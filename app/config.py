"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost", "::1")
"""Host interfaces the server is allowed to bind to (local-only)."""

WIPE_CONFIRM_TEXT: str = "WIPE ALL DATA"
"""Exact confirmation text required for full database wipes."""

DESTRUCTIVE_CONFIRM_HEADER: str = "X-Confirm-Delete"
"""Custom header that must accompany destructive API calls."""


BASE_DIR: Path = Path(__file__).resolve().parent.parent
"""Project root directory (pod-automation/)."""


class Settings(BaseSettings):
    """Typed application settings loaded from environment and `.env` file."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "POD Facebook Automation Dashboard"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    # Local-only CORS origins (no wildcards). Extra dev ports included so the
    # dashboard still works from localhost Vite/preview servers.
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    )

    @field_validator("HOST")
    @classmethod
    def _validate_local_host(cls, value: str) -> str:
        """Refuse non-local bind addresses (audit hardening)."""
        host = (value or "").strip()
        if host not in LOCAL_HOSTS:
            raise ValueError(
                f"HOST must be a local address {list(LOCAL_HOSTS)}, got {value!r}."
            )
        return host
    DATABASE_URL: str = "sqlite:///./data/automation.db"
    AI_PROVIDER: str = "groq"
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_TEMPERATURE: float = 0.8
    AI_MAX_TOKENS: int = 800
    AI_TIMEOUT_SECONDS: int = 30
    AI_MAX_RETRIES: int = 3
    AI_FALLBACK_ENABLED: bool = True
    AI_MOCK_MODE: bool = False
    DEFAULT_POST_LANGUAGE: str = "English"
    DEFAULT_BRAND_VOICE: str = "friendly, witty, and persuasive"
    FACEBOOK_PAGE_ID: str = ""
    FACEBOOK_PAGE_ACCESS_TOKEN: str = ""
    FACEBOOK_GRAPH_VERSION: str = "v21.0"
    FACEBOOK_DRY_RUN: bool = True
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = Field(default=30, ge=10)
    SCHEDULER_BATCH_SIZE: int = 5
    PUBLISH_MAX_ATTEMPTS: int = 3
    LOG_LEVEL: str = "INFO"

    def has_provider_key(self, provider: str) -> bool:
        """Return True only if the provider has a usable (non-placeholder) key."""
        name = (provider or "").strip().lower()
        if name == "groq":
            key = self.GROQ_API_KEY
        elif name == "openai":
            key = self.OPENAI_API_KEY
        else:
            return False
        if not key or not key.strip():
            return False
        lowered = key.strip().lower()
        placeholders = (
            "your_",
            "your-",
            "sk-xxx",
            "gsk_xxx",
            "gsk-xxx",
            "placeholder",
            "changeme",
            "test-key",
        )
        if lowered.startswith(placeholders):
            return False
        return True

    def has_facebook_credentials(self) -> bool:
        """Return True only if Page ID and token are set and not placeholders."""
        page_id = (self.FACEBOOK_PAGE_ID or "").strip()
        token = (self.FACEBOOK_PAGE_ACCESS_TOKEN or "").strip()
        if not page_id or not token:
            return False
        placeholders = ("your_", "your-", "placeholder", "changeme", "test")
        lowered_id = page_id.lower()
        lowered_token = token.lower()
        if lowered_id.startswith(placeholders) or lowered_token.startswith(placeholders):
            return False
        return True


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
