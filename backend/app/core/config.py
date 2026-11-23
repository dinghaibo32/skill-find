"""Application settings loaded from environment variables / .env file.

LLM-related settings are reserved here so future model integrations
only need to read from `get_settings()` instead of os.environ directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration. Override via environment or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "skill-find"
    app_version: str = "0.1.0"

    # CORS origins allowed to call the API directly (dev frontend uses a proxy).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- LLM settings (OpenAI-compatible provider, configured via .env) ---
    # Any OpenAI-compatible endpoint works: OpenAI, DeepSeek, Qwen, Ollama, etc.
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    # Pricing in CNY per 1M tokens; adjust together with llm_model.
    llm_input_price_per_million: float = 0.8
    llm_output_price_per_million: float = 2.0


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; use as a FastAPI dependency when needed."""
    return Settings()
