"""Facebook error hierarchy with secret redaction."""

from typing import Optional

from app.config import get_settings


def redact_token_text(text: str) -> str:
    """Replace the configured Facebook token in text with ***."""
    safe = str(text)
    try:
        token = get_settings().FACEBOOK_PAGE_ACCESS_TOKEN or ""
    except Exception:
        token = ""
    if token:
        safe = safe.replace(token, "***")
    return safe


class FacebookError(Exception):
    """Base error for Facebook Graph API failures (message always redacted)."""

    def __init__(
        self, message: str, code: Optional[int] = None, retryable: bool = False
    ) -> None:
        """Store a redacted message, numeric code and retry flag."""
        self.message: str = redact_token_text(message)
        self.code: Optional[int] = code
        self.retryable: bool = retryable
        super().__init__(self.message)


class FacebookAuthError(FacebookError):
    """Token invalid or expired; never retryable."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        """Store an auth failure message."""
        super().__init__(message, code=code, retryable=False)


class FacebookRateLimitError(FacebookError):
    """Rate limit hit; retryable after a backoff."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        """Store a rate-limit failure message."""
        super().__init__(message, code=code, retryable=True)


class FacebookConfigError(FacebookError):
    """Credentials missing or mismatched; never retryable."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        """Store a configuration failure message."""
        super().__init__(message, code=code, retryable=False)
