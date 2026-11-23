"""LLM client for any OpenAI-compatible /chat/completions endpoint.

Works with OpenAI, DeepSeek, Qwen (DashScope compatible mode), Ollama,
vLLM, etc. Only `base_url`, `api_key` and `model` differ per vendor.
"""

import httpx

from app.services.llm.base import ChatMessage, LLMError, LLMNotConfiguredError


class OpenAICompatibleClient:
    """Async client speaking the OpenAI chat completions protocol."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def chat(self, messages: list[ChatMessage]) -> str:
        """Call /chat/completions and return the first reply content."""
        if not self._api_key:
            raise LLMNotConfiguredError(
                "LLM API key is not configured. Set LLM_API_KEY in backend/.env."
            )

        payload = {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {data}") from exc