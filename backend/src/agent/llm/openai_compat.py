import json

from openai import AsyncOpenAI

from src.agent.llm.base import BaseLLMClient
from src.config import settings


class OpenAICompatClient(BaseLLMClient):
    """Client for any OpenAI-compatible endpoint (e.g. Gemini's /v1beta/openai/)."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        response = await self._client.chat.completions.create(
            model=settings.llm_model, messages=messages, tools=tools
        )
        message = response.choices[0].message
        tool_calls = []
        for call in message.tool_calls or []:
            raw = call.function.arguments
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": json.loads(raw) if raw else {},
                    # Gemini's thought_signature: must be echoed back on the next turn.
                    "extra_content": (call.model_extra or {}).get("extra_content"),
                }
            )
        usage = response.usage
        return {
            "content": message.content,
            "tool_calls": tool_calls,
            "tokens_in": usage.prompt_tokens if usage else None,
            "tokens_out": usage.completion_tokens if usage else None,
            "model": response.model,
        }
