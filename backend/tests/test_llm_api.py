"""Tests for POST /api/llm/chat using a fake LLM client."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.llm import get_llm_client
from app.services.llm.base import ChatResult, LLMError, LLMNotConfiguredError, LLMUsage


class _FakeClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def chat(self, messages):
        if self._error is not None:
            raise self._error
        return self._result


def _client_with(fake):
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: fake
    return TestClient(app)


def _result():
    return ChatResult(
        content="hello there",
        model="qwen-plus",
        usage=LLMUsage(input_tokens=12, output_tokens=34, total_tokens=46, cost=0.000078),
    )


def _payload():
    return {"messages": [{"role": "user", "content": "hi"}]}


def test_chat_returns_reply_and_usage():
    client = _client_with(_FakeClient(result=_result()))
    response = client.post("/api/llm/chat", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "hello there"
    assert body["model"] == "qwen-plus"
    assert body["usage"] == {
        "input_tokens": 12,
        "output_tokens": 34,
        "total_tokens": 46,
        "cost": 0.000078,
    }


def test_chat_not_configured_returns_503():
    client = _client_with(_FakeClient(error=LLMNotConfiguredError("no key")))
    response = client.post("/api/llm/chat", json=_payload())
    assert response.status_code == 503


def test_chat_upstream_failure_returns_502():
    client = _client_with(_FakeClient(error=LLMError("boom")))
    response = client.post("/api/llm/chat", json=_payload())
    assert response.status_code == 502


def test_chat_empty_messages_returns_422():
    client = _client_with(_FakeClient(result=_result()))
    response = client.post("/api/llm/chat", json={"messages": []})
    assert response.status_code == 422
