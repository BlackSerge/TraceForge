from src.agent.llm.base import BaseLLMClient
from src.agent.llm.google_native import GoogleNativeClient
from src.agent.llm.openai_compat import OpenAICompatClient
from src.config import settings


def get_llm_client() -> BaseLLMClient:
    if settings.llm_provider == "openai_compat":
        return OpenAICompatClient()
    if settings.llm_provider == "google_native":
        return GoogleNativeClient()
    raise ValueError(
        f"Unknown llm_provider {settings.llm_provider!r}; expected 'openai_compat' or 'google_native'"
    )
