"""AI error classification matrix (auth vs rate-limit vs generic)."""

from app.services.ai.exceptions import (
    AIAuthError,
    AIProviderError,
    AIRateLimitError,
    classify_provider_error,
)


def test_401_maps_to_auth_error():
    assert isinstance(
        classify_provider_error("groq", Exception("401 Unauthorized")), AIAuthError
    )


def test_403_maps_to_auth_error():
    assert isinstance(
        classify_provider_error("openai", Exception("403 forbidden")), AIAuthError
    )


def test_429_maps_to_rate_limit_error():
    assert isinstance(
        classify_provider_error("groq", Exception("429 rate_limit exceeded")),
        AIRateLimitError,
    )


def test_generic_error_maps_to_provider_error():
    err = classify_provider_error("groq", Exception("connection reset"))
    assert isinstance(err, AIProviderError)
    assert not isinstance(err, (AIAuthError, AIRateLimitError))
