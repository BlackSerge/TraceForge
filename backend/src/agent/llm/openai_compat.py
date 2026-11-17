import asyncio
import json

from openai import APIStatusError, APITimeoutError, AsyncOpenAI

from src.agent.llm.base import BaseLLMClient
from src.config import settings


RETRY_STATUSES = {429, 503}
MAX_RETRIES = 3
BACKOFF_BASE_S = 5.0  # waits 5s, 10s, 20s
REQUEST_TIMEOUT_S = 60.0


class OpenAICompatClient(BaseLLMClient):
    """Client for any OpenAI-compatible endpoint (e.g. Gemini's /v1beta/openai/)."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key, base_url=settings.llm_base_url,
            max_retries=0, timeout=REQUEST_TIMEOUT_S,
        )

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=settings.llm_model, messages=messages, tools=tools
                )
                break
            except (APIStatusError, APITimeoutError) as exc:
                retryable = isinstance(exc, APITimeoutError) or exc.status_code in RETRY_STATUSES
                if not retryable or attempt == MAX_RETRIES:
                    raise
                await asyncio.sleep(BACKOFF_BASE_S * 2**attempt)
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
