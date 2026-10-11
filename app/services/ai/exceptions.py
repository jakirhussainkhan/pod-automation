"""AI service exception hierarchy."""


class AIServiceError(Exception):
    """Base error for all AI service failures."""


class AIProviderError(AIServiceError):
    """A provider call failed; carries the provider name."""

    def __init__(self, provider: str, message: str) -> None:
        """Store the provider name alongside a readable message."""
        self.provider: str = provider
        super().__init__(f"[{provider}] {message}")


class AIConfigurationError(AIServiceError):
    """No usable provider or API key is configured."""


class AIAuthError(AIProviderError):
    """Provider rejected the API key (401/403). No retry helps."""


class AIRateLimitError(AIProviderError):
    """Provider rate-limited the request (429). Back off before retrying."""


class AIResponseParseError(AIServiceError):
    """The model output was invalid or contained no parseable JSON."""


def classify_provider_error(provider: str, exc: Exception) -> AIServiceError:
    """Map transport/SDK errors to typed AI errors (auth vs rate-limit vs generic)."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(token in text for token in ("401", "403", "unauthorized", "invalid_api_key", "invalid api key", "authentication")):
        return AIAuthError(provider, f"authentication failed: {exc}")
    if any(token in text for token in ("429", "rate_limit", "rate limit", "too many requests", "quota")):
        return AIRateLimitError(provider, f"rate limited: {exc}")
    if isinstance(exc, AIServiceError):
        return exc
    return AIProviderError(provider, f"request failed: {exc}")
