"""Application settings — reads all env vars from .env at startup."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file so uvicorn can be started from any cwd.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_secret_key: str

    # OpenRouter
    openrouter_api_key: str
    # Base URL — has a default so it does not need to appear in .env unless overriding
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default model used by the orchestrator (Phase 3+). Override via LLM_MODEL in .env.
    llm_model: str = "anthropic/claude-3.5-sonnet"

    # JWT — must match Supabase Dashboard → Settings → API → JWT Secret
    jwt_secret_key: str

    # Encryption (Phase 5) — Fernet key (urlsafe base64, 32 bytes).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Used to encrypt memory_entries.content_encrypted at rest.
    encryption_key: str

    # Embeddings (Phase 5) — OpenRouter routes this to OpenAI's embeddings API.
    # Dimensions must match the DB schema (extensions.vector(1536)).
    embedding_model: str = "openai/text-embedding-3-large"
    embedding_dimensions: int = 1536

    # YouTube agent (Phase 10) — model used for hierarchical transcript summarization.
    # Uses a fast, large-context model via OpenRouter; not the user's selected chat model.
    youtube_summary_model: str = "google/gemini-2.5-flash"

    # Rate limiting — optional Redis backend for multi-worker deployments.
    # Leave unset (default None) to use in-memory storage (single process).
    # Example: redis://localhost:6379/0
    redis_url: str | None = None

    # CORS — comma-separated list of allowed origins.
    # Example: http://localhost:3000,https://axon.example.com
    cors_origins: list[str] = ["http://localhost:3000"]

    # Server
    debug: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),  # absolute path — works regardless of cwd
        env_file_encoding="utf-8",
        case_sensitive=False,  # SUPABASE_URL == supabase_url
    )


# Singleton — import this everywhere: from app.core.config import settings
settings = Settings()
