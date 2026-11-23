"""LLM client for any OpenAI-compatible endpoint, built on the openai SDK.

Works with OpenAI, DeepSeek, Qwen (DashScope compatible mode), Ollama,
vLLM, etc. Only `base_url`, `api_key`, `model` and prices differ per vendor.
"""

from openai import APIError, AsyncOpenAI

from app.services.llm.base import (
    ChatMessage,
    ChatResult,
    LLMError,
    LLMNotConfiguredError,
    LLMUsage,
)


class OpenAICompatibleClient:
    """Async client speaking the OpenAI chat completions protocol."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        input_price_per_million: float = 0.0,
        output_price_per_million: float = 0.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._input_price = input_price_per_million
        self._output_price = output_price_per_million

    async def chat(self, messages: list[ChatMessage]) -> ChatResult:
        """Call chat completions and return the reply with usage statistics."""
        if not self._api_key:
            raise LLMNotConfiguredError(
                "LLM API key is not configured. Set LLM_API_KEY in backend/.env."
            )

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[message.model_dump() for message in messages],
            )
        except APIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        finally:
            await client.close()

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {response}") from exc
        if content is None:
            raise LLMError("LLM response has empty content")

        usage = response.usage
        if usage is None:
            raise LLMError("LLM response is missing usage statistics")
        try:
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            total_tokens = (
                usage.total_tokens
                if usage.total_tokens is not None
                else input_tokens + output_tokens
            )
            cost = round(
                input_tokens / 1_000_000 * self._input_price
                + output_tokens / 1_000_000 * self._output_price,
                6,
            )
        except (AttributeError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM usage shape: {usage}") from exc
        return ChatResult(
            content=content,
            model=self._model,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost,
            ),
        )
