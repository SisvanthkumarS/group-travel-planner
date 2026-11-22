import json
import logging
from collections.abc import Mapping, Sequence
from time import monotonic
from typing import Protocol

from openai import APITimeoutError, OpenAI
from openai.types.responses import EasyInputMessageParam
from pydantic import SecretStr, ValidationError

from backend.app.core.config import OpenAiApiMode, get_settings
from backend.app.schemas.AiChat import AiChatModelReply

logger = logging.getLogger(__name__)

TRAVEL_ASSISTANT_INSTRUCTIONS = """
You help members plan their shared trip. Reply in the user's language.
Use the supplied current time, trip dates, timezone, destination, and itinerary as context.
Use earlier messages as context and answer the final user message. Earlier group
messages may be prefixed with a Trip member identifier to distinguish speakers.
Only use the final request to decide whether the user is asking for a draft.

Return a JSON object with exactly two fields:
- "content": A non-blank string containing the reply shown to the user.
- "draft": null by default. Return an object with exactly "kind" and "proposals"
  only when the user explicitly asks you to generate a proposal, suggest
  activities as proposals, or draft an itinerary. A clear revision request
  referring to a previously requested draft also qualifies.

Answer ordinary questions in "content" and set "draft" to null. This applies
to general recommendations, brainstorming, comparisons, and logistics questions,
even when the answer mentions specific activities or times. For example,
"What can I do in Central Park?" gets a normal answer with "draft": null.
"Create a proposal for a Central Park walk" requests a draft. When the
intent is ambiguous, ask whether the user wants a draft and set "draft" to null.

Example ordinary question: "Can you suggest things to do in New York?"
Example JSON answer:
{
  "content": "Consider Central Park, a museum, or Brooklyn Bridge. What interests your group?",
  "draft": null
}
Return the complete JSON object for every answer, including ordinary questions.

Set "kind" to "PROPOSAL" for exactly one activity, or "ITINERARY" for
2 to 100 activities. "proposals" is an array of objects. Each object must
include exactly these six fields:
- "title": A short, non-blank string naming the activity.
- "description": A non-blank string describing the plan.
- "location": A non-blank string naming the venue or area.
- "estimated_cost": A finite, nonnegative decimal written as a JSON string
  using a dot as the decimal separator, such as "25.50" or "0". Omit currency
  symbols and thousands separators. Explain the currency in "content" when relevant.
- "starts_at": A future ISO 8601 datetime string with an explicit UTC offset,
  such as "2030-07-12T10:00:00-04:00".
- "ends_at": An ISO 8601 datetime string in the same format, strictly later
  than "starts_at".

Use the UTC offset for the trip's timezone on each activity date. Both
timestamps must fall within the inclusive travel dates in that timezone.
Avoid overlaps with the existing itinerary and between proposed activities.
Explain estimates or assumptions in content. Ask for clarification if necessary.
Drafts are suggestions for the user to review. Never claim they have been submitted.

Example for a trip to New York on July 12, 2030. Use the actual trip context
and user request to choose the values for each reply.
{
  "content": "I suggest a morning walk in Central Park. The walk itself is free.",
  "draft": {
    "kind": "PROPOSAL",
    "proposals": [
      {
        "title": "Central Park walk",
        "description": "Walk from Bethesda Terrace to the Bow Bridge.",
        "location": "Central Park, New York",
        "estimated_cost": "0.00",
        "starts_at": "2030-07-12T10:00:00-04:00",
        "ends_at": "2030-07-12T11:30:00-04:00"
      }
    ]
  }
}
""".strip()


class AiChatClient(Protocol):
    """Provider contract. Adapters must validate output as AiChatModelReply."""

    def generate(
        self,
        *,
        messages: Sequence[Mapping[str, str]],
        trip_context: Mapping[str, object],
    ) -> AiChatModelReply: ...


class OpenAiChatClient:
    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        *,
        base_url: str,
        api_mode: OpenAiApiMode,
    ):
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url
        self._api_mode = api_mode

    def generate(
        self,
        *,
        messages: Sequence[Mapping[str, str]],
        trip_context: Mapping[str, object],
    ) -> AiChatModelReply:
        inputs: list[EasyInputMessageParam] = [
            {
                "role": "user",
                "content": f"Current trip context (JSON):\n{json.dumps(dict(trip_context))}",
            }
        ]
        for message in messages:
            role = message["role"]
            if role not in ("user", "assistant"):
                raise ValueError("Unsupported chat message role.")
            content = message["content"]
            if self._api_mode == "chat_completions" and role == "assistant":
                # Stored history contains display text. Match the JSON answer
                # format when sending earlier assistant turns back to JSON mode.
                content = json.dumps({"content": content, "draft": None}, ensure_ascii=False)
            inputs.append({"role": role, "content": content})

        try:
            with OpenAI(
                api_key=self._api_key.get_secret_value(),
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                max_retries=0,
            ) as client:
                if self._api_mode == "chat_completions":
                    return self._generate_chat_completion(client, inputs)

                response = client.responses.parse(
                    model=self._model,
                    instructions=TRAVEL_ASSISTANT_INSTRUCTIONS,
                    input=inputs,
                    text_format=AiChatModelReply,
                    store=False,
                )
        except APITimeoutError as exc:
            raise TimeoutError("AI provider request timed out.") from exc

        if response.status != "completed" or response.output_parsed is None:
            raise ValueError("AI provider did not return a complete chat reply.")
        return response.output_parsed

    def _generate_chat_completion(
        self, client: OpenAI, inputs: list[EasyInputMessageParam]
    ) -> AiChatModelReply:
        deadline = monotonic() + self._timeout_seconds
        instructions = TRAVEL_ASSISTANT_INSTRUCTIONS
        for attempt in range(2):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("AI provider request timed out.")
            completion = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": instructions}, *inputs],
                response_format={"type": "json_object"},
                timeout=remaining,
            )
            if not completion.choices:
                raise ValueError("AI provider returned no reply.")
            choice = completion.choices[0]
            if choice.finish_reason != "stop":
                raise ValueError("AI provider did not return a complete chat reply.")
            try:
                return AiChatModelReply.model_validate_json(choice.message.content or "")
            except ValidationError as exc:
                logger.warning(
                    "AI JSON validation failed (attempt=%s, blank=%s, error_types=%s).",
                    attempt + 1,
                    not (choice.message.content or "").strip(),
                    [error["type"] for error in exc.errors(include_input=False)],
                )
                if attempt == 1:
                    raise
                instructions += (
                    "\nA previous generation failed JSON validation. Produce a complete JSON "
                    "object with a non-empty content string and draft. For general advice "
                    "use draft: null. Return JSON directly without Markdown fences."
                )
        raise RuntimeError("AI generation attempts exhausted.")


def get_ai_chat_client() -> AiChatClient | None:
    settings = get_settings()
    api_key = settings.openai_api_key
    if api_key is None or not api_key.get_secret_value().strip():
        return None
    return OpenAiChatClient(
        api_key,
        settings.openai_model,
        settings.openai_timeout_seconds,
        base_url=str(settings.openai_base_url),
        api_mode=settings.openai_api_mode,
    )
