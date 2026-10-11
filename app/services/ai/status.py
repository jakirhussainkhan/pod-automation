"""AI provider status reporting for the dashboard."""

from app.config import get_settings
from app.schemas.ai import AIStatusResponse


def get_ai_status() -> AIStatusResponse:
    """Report configured providers, fallback availability and mock mode."""
    settings = get_settings()
    groq_ok = settings.has_provider_key("groq")
    openai_ok = settings.has_provider_key("openai")
    if settings.AI_MOCK_MODE:
        return AIStatusResponse(
            primary_provider="mock",
            fallback_provider=None,
            mock_mode=True,
            groq_configured=groq_ok,
            openai_configured=openai_ok,
        )
    primary = (settings.AI_PROVIDER or "groq").strip().lower() or "groq"
    if primary not in ("groq", "openai"):
        # Keep the misconfigured value visible (don't silently report "groq")
        # so status matches factory.get_provider_chain() which raises 503.
        return AIStatusResponse(
            primary_provider=primary,
            fallback_provider=None,
            mock_mode=False,
            groq_configured=groq_ok,
            openai_configured=openai_ok,
        )
    other = "openai" if primary == "groq" else "groq"
    other_ok = settings.has_provider_key(other)
    fallback = other if (settings.AI_FALLBACK_ENABLED and other_ok) else None
    return AIStatusResponse(
        primary_provider=primary,
        fallback_provider=fallback,
        mock_mode=False,
        groq_configured=groq_ok,
        openai_configured=openai_ok,
    )
