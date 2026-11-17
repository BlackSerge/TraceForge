from src.agent.llm.base import BaseLLMClient
from src.config import settings


class GoogleNativeClient(BaseLLMClient):
    """Stub for the native Google client.

    It will be implemented with the `google-genai` SDK in the future. Until then,
    use the `openai_compat` provider (Gemini exposes an OpenAI-compatible endpoint).
    """

    def __init__(self) -> None:
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        raise NotImplementedError("Google native client pending. Use openai_compat for now.")
