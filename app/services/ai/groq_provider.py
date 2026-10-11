"""Groq AI provider using the official groq SDK."""

from typing import Optional

from app.config import get_settings
from app.services.ai.base import AIResult, BaseAIProvider
from app.services.ai.exceptions import AIProviderError


class GroqProvider(BaseAIProvider):
    """Chat completion provider backed by Groq."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """Resolve credentials, model and timeout from args or settings."""
        settings = get_settings()
        self.name: str = "groq"
        self.model: str = model or settings.GROQ_MODEL
        self._api_key: str = api_key or settings.GROQ_API_KEY
        self._timeout: int = timeout if timeout is not None else settings.AI_TIMEOUT_SECONDS

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> AIResult:
        """Call the Groq chat API and wrap the response as an AIResult."""
        try:
            from groq import Groq

            client = Groq(api_key=self._api_key, timeout=self._timeout)
            kwargs: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
        except AIProviderError:
            raise
        except Exception as exc:
            from app.services.ai.exceptions import classify_provider_error

            raise classify_provider_error(self.name, exc) from exc
        try:
            text = (response.choices[0].message.content or "").strip()
        except (AttributeError, IndexError) as exc:
            raise AIProviderError(self.name, f"empty response structure: {exc}") from exc
        if not text:
            raise AIProviderError(self.name, "empty response content")
        tokens: Optional[int] = None
        try:
            usage = getattr(response, "usage", None)
            if usage is not None and getattr(usage, "total_tokens", None) is not None:
                tokens = int(usage.total_tokens)
        except (TypeError, ValueError):
            tokens = None
        return AIResult(text=text, provider=self.name, model=self.model, tokens_used=tokens)
