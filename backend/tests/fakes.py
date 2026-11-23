"""Shared scripted fake LLM client for agent and eval tests."""

from app.services.llm.base import ChatResult, LLMUsage, ToolChatResult


def fake_usage(input_tokens: int = 100, output_tokens: int = 50) -> LLMUsage:
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost=0.00018,
    )


class FakeLLM:
    """Pops one scripted item per call; Exception items are raised."""

    def __init__(self, chat_replies=None, tool_replies=None):
        self.chat_replies = list(chat_replies or [])
        self.tool_replies = list(tool_replies or [])
        self.chat_calls: list = []
        self.tool_calls_received: list = []

    async def chat(self, messages):
        self.chat_calls.append(messages)
        if not self.chat_replies:
            return ChatResult(content="default reply", model="fake", usage=fake_usage())
        item = self.chat_replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResult(content=item, model="fake", usage=fake_usage())

    async def chat_with_tools(self, messages, tools):
        self.tool_calls_received.append(messages)
        if not self.tool_replies:
            return ToolChatResult(
                content="default reply", tool_calls=[], model="fake", usage=fake_usage()
            )
        item = self.tool_replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
