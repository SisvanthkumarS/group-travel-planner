import json

import httpx
import pytest
from openai import OpenAI

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
        assert request.extensions["timeout"]["read"] == 12
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
        messages=[{"role": "user", "content": "What can we do?"}],
        trip_context={"destination": "NYC"},
    )
    assert reply.model_dump(mode="json") == {
        "content": "Visit the park.",
        "draft": draft,
    }
