"""Application settings — reads all env vars from .env at startup."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_secret_key: str

    # OpenRouter
    openrouter_api_key: str

    # JWT — must match Supabase Dashboard → Settings → API → JWT Secret
    jwt_secret_key: str

    # Server
    debug: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",  # loaded relative to the cwd (backend/)
        env_file_encoding="utf-8",
        case_sensitive=False,  # SUPABASE_URL == supabase_url
    )


# Singleton — import this everywhere: from app.core.config import settings
settings = Settings()
