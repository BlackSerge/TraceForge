from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """Provider-agnostic chat client.

    `chat` returns a dict with:
      - content: str | None
      - tool_calls: list[{"id": str | None, "name": str, "arguments": dict}]
      - tokens_in: int | None
      - tokens_out: int | None
      - model: str
    """

    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict]) -> dict: ...
