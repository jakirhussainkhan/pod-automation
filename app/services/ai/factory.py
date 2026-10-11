"""Provider selection with optional fallback chain."""

from typing import Optional

from app.config import get_settings
from app.services.ai.base import BaseAIProvider
from app.services.ai.exceptions import AIConfigurationError
from app.services.ai.groq_provider import GroqProvider
from app.services.ai.mock_provider import MockProvider
from app.services.ai.openai_provider import OpenAIProvider

_KNOWN_PROVIDERS: tuple[str, ...] = ("groq", "openai")


def _build_provider(name: str) -> BaseAIProvider:
    """Instantiate a real provider by name after validating its key."""
    settings = get_settings()
    if name == "groq":
        if not settings.has_provider_key("groq"):
            raise AIConfigurationError("Groq API key is missing or looks like a placeholder.")
        return GroqProvider()
    if name == "openai":
        if not settings.has_provider_key("openai"):
            raise AIConfigurationError("OpenAI API key is missing or looks like a placeholder.")
        return OpenAIProvider()
    raise AIConfigurationError(f"Unknown AI provider: {name!r}. Use 'groq' or 'openai'.")


def get_provider(name: Optional[str] = None) -> BaseAIProvider:
    """Return the requested provider (or first of the fallback chain)."""
    settings = get_settings()
    if settings.AI_MOCK_MODE:
        return MockProvider()
    if name:
        return _build_provider(name.strip().lower())
    # No explicit name: use the first usable provider in the fallback chain
    # so callers benefit from fallback instead of raising when primary is down.
    return get_provider_chain()[0]


def get_provider_chain() -> list[BaseAIProvider]:
    """Return primary plus optional fallback provider, never empty."""
    settings = get_settings()
    if settings.AI_MOCK_MODE:
        return [MockProvider()]
    primary = (settings.AI_PROVIDER or "groq").strip().lower()
    if primary not in _KNOWN_PROVIDERS:
        raise AIConfigurationError(
            f"Unknown AI provider: {primary!r}. Use 'groq' or 'openai'."
        )
    chain: list[BaseAIProvider] = []
    if settings.has_provider_key(primary):
        chain.append(_build_provider(primary))
    if settings.AI_FALLBACK_ENABLED:
        fallback = "openai" if primary == "groq" else "groq"
        if settings.has_provider_key(fallback):
            chain.append(_build_provider(fallback))
    if not chain:
        raise AIConfigurationError(
            "No AI provider is configured: set a valid GROQ_API_KEY and/or "
            "OPENAI_API_KEY, or enable AI_MOCK_MODE."
        )
    return chain
