import json
from unittest.mock import Mock

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr, ValidationError

from backend.app.core import AiChatClient as chat_client
from backend.app.core.config import Settings


@pytest.mark.parametrize(
    "draft",
    [
        None,
        {
            "kind": "PROPOSAL",
            "proposals": [
                {
                    "title": "Park",
                    "description": "Walk",
                    "estimated_cost": "0",
                    "location": "NYC",
                    "starts_at": "2030-01-01T09:00:00-05:00",
                    "ends_at": "2030-01-01T10:00:00-05:00",
                }
            ],
        },
    ],
)
@pytest.mark.parametrize("mode", ["responses", "chat_completions"])
def test_openai_adapter_reads_dotenv_and_parses_reply(
    monkeypatch, tmp_path, draft, mode
):
    for variable in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_MODE",
        "OPENAI_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(variable, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=example-test-key\n"
        "OPENAI_BASE_URL=https://provider.example/custom/v1\n"
        f"OPENAI_API_MODE={mode}\n"
        "OPENAI_MODEL=example-model\n"
        "OPENAI_TIMEOUT_SECONDS=12\n"
    )
    monkeypatch.setattr(
        chat_client, "get_settings", lambda: Settings(_env_file=env_file)
    )

    def respond(request):
        assert request.url.host == "provider.example"
        assert request.headers["Authorization"] == "Bearer example-test-key"
        assert 0 < request.extensions["timeout"]["read"] <= 12
        body = json.loads(request.content)
        assert body["model"] == "example-model"
        output = json.dumps({"content": "Visit the park.", "draft": draft})
        if mode == "chat_completions":
            assert request.url.path == "/custom/v1/chat/completions"
            assert body["response_format"] == {"type": "json_object"}
            assert body["messages"][0]["role"] == "system"
            assert "NYC" in body["messages"][1]["content"]
            assert body["messages"][-1] == {
                "role": "user",
                "content": "What can we do?",
            }
            assert json.loads(body["messages"][-2]["content"]) == {
                "content": "Your trip has a park walk.",
                "draft": None,
            }
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": output},
                        },
                    ]
                },
            )

        assert request.url.path == "/custom/v1/responses"
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["input"][-1] == {"role": "user", "content": "What can we do?"}
        assert "NYC" in body["input"][0]["content"]
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": output,
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        chat_client,
        "OpenAI",
        lambda **kwargs: OpenAI(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))
        ),
    )
    provider = chat_client.get_ai_chat_client()
    assert provider is not None
    reply = provider.generate(
        messages=[
            {"role": "user", "content": "Read the itinerary."},
            {"role": "assistant", "content": "Your trip has a park walk."},
            {"role": "user", "content": "What can we do?"},
        ],
        trip_context={"destination": "NYC"},
    )
    assert reply.model_dump(mode="json") == {
        "content": "Visit the park.",
        "draft": draft,
    }


@pytest.mark.parametrize("invalid_output", [" \n" * 100, '{"content": "unfinished'])
def test_chat_completion_recovers_invalid_json_within_original_timeout(
    monkeypatch, invalid_output
):
    sdk = Mock()
    sdk.__enter__ = Mock(return_value=sdk)
    sdk.__exit__ = Mock(return_value=False)
    outputs = [
        invalid_output,
        '{"content":"Consider Central Park.","draft":null}',
    ]
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        result = Mock()
        result.choices = [
            Mock(finish_reason="stop", message=Mock(content=outputs.pop(0)))
        ]
        return result

    sdk.chat.completions.create.side_effect = complete
    monkeypatch.setattr(chat_client, "OpenAI", lambda **kwargs: sdk)
    monkeypatch.setattr(chat_client, "monotonic", Mock(side_effect=[100, 100, 105]))
    provider = chat_client.OpenAiChatClient(
        SecretStr("test-key"),
        "example-model",
        12,
        base_url="https://provider.example",
        api_mode="chat_completions",
    )
    reply = provider.generate(
        messages=[{"role": "user", "content": "Suggest places in New York."}],
        trip_context={},
    )
    assert reply.content == "Consider Central Park." and reply.draft is None
    assert [call["timeout"] for call in calls] == [12, 7]
    assert calls[0]["messages"][1:] == calls[1]["messages"][1:]


def test_chat_completion_does_not_retry_forever_or_accept_blank_reply(monkeypatch):
    sdk = Mock()
    sdk.__enter__ = Mock(return_value=sdk)
    sdk.__exit__ = Mock(return_value=False)
    result = Mock()
    result.choices = [Mock(finish_reason="stop", message=Mock(content=" \n" * 100))]
    sdk.chat.completions.create.return_value = result
    monkeypatch.setattr(chat_client, "OpenAI", lambda **kwargs: sdk)
    provider = chat_client.OpenAiChatClient(
        SecretStr("test-key"),
        "example-model",
        12,
        base_url="https://provider.example",
        api_mode="chat_completions",
    )
    with pytest.raises(ValidationError):
        provider.generate(
            messages=[{"role": "user", "content": "Hello"}], trip_context={}
        )
    assert sdk.chat.completions.create.call_count == 2
