from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://devpilot:devpilot@localhost:5433/devpilot"
    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "openai_compat"
    llm_api_key: SecretStr  # required: no default, startup fails if missing
    llm_base_url: str
    llm_model: str

    eval_sleep_between_cases_s: float = 5.0


settings = Settings()
