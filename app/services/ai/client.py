"""Provider orchestration with retries, fallback and DB recording."""

import logging
import time
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import ai_generation_service
from app.services.ai.base import AIResult
from app.services.ai.exceptions import (
    AIAuthError,
    AIProviderError,
    AIRateLimitError,
    AIResponseParseError,
)
from app.services.ai.factory import get_provider_chain

logger = logging.getLogger("pod-automation")

_RETRY_NOTE = "Your previous reply was not valid JSON. Reply with ONLY the JSON object."


def _safe_record(db: Session, *args, **kwargs) -> None:
    """Record a generation attempt without masking the original AI error.

    Positional layout mirrors ``record_generation``:
    (product_id, prompt, response, provider, model, tokens, success).
    """
    call_type = kwargs.pop("call_type", "other")
    # Resolve metering fields before the record call consumes anything.
    provider = kwargs.get("provider", args[3] if len(args) > 3 else "mock")
    model = kwargs.get("model", args[4] if len(args) > 4 else "")
    raw_tokens = kwargs.get("tokens_used", args[5] if len(args) > 5 else 0)
    success = kwargs.get("success", args[6] if len(args) > 6 else True)
    try:
        ai_generation_service.record_generation(db, *args, **kwargs)
    except Exception:
        logger.exception("Failed to record AI generation attempt.")
        try:
            db.rollback()
        except Exception:
            pass
    # Best-effort usage metering; never breaks the AI flow.
    try:
        from app.services import ai_usage_service

        try:
            total = max(0, int(raw_tokens or 0))
        except (TypeError, ValueError):
            total = 0
        ai_usage_service.record_ai_call(
            db,
            provider=provider,
            model=model,
            call_type=call_type,
            tokens_in=0,
            tokens_out=total,
            success=bool(success),
            error_type=None if success else "provider_error",
        )
    except Exception:
        logger.exception("Failed to meter AI usage (flow continues).")


def _combined_prompt(system_prompt: str, user_prompt: str) -> str:
    """Combine system and user prompts for generation logging."""
    return f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"


def run_with_fallback(
    db: Session,
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = True,
    product_id: Optional[int] = None,
    call_type: str = "other",
) -> AIResult:
    """Try each provider with retries and return the first success."""
    settings = get_settings()
    chain = get_provider_chain()
    max_retries = max(1, settings.AI_MAX_RETRIES)
    combined = _combined_prompt(system_prompt, user_prompt)
    failures: list[str] = []
    for provider in chain:
        for attempt in range(1, max_retries + 1):
            try:
                result = provider.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=settings.AI_TEMPERATURE,
                    max_tokens=settings.AI_MAX_TOKENS,
                    json_mode=json_mode,
                )
                _safe_record(
                    db,
                    product_id,
                    combined,
                    result.text,
                    provider.name,
                    provider.model,
                    result.tokens_used,
                    True,
                    call_type=call_type,
                )
                return result
            except AIAuthError as exc:
                # Bad key: retrying the same provider cannot help; try fallback.
                _safe_record(
                    db,
                    product_id,
                    combined,
                    f"ERROR: {exc}",
                    provider.name,
                    provider.model,
                    None,
                    False,
                    call_type=call_type,
                )
                failures.append(f"{provider.name} auth failed: {exc}")
                logger.warning("AI auth failed, skipping retries: %s", exc)
                break
            except (AIRateLimitError, AIProviderError) as exc:
                _safe_record(
                    db,
                    product_id,
                    combined,
                    f"ERROR: {exc}",
                    provider.name,
                    provider.model,
                    None,
                    False,
                    call_type=call_type,
                )
                failures.append(f"{provider.name} attempt {attempt}/{max_retries}: {exc}")
                logger.warning("AI attempt failed: %s", exc)
                if attempt < max_retries and not settings.AI_MOCK_MODE:
                    time.sleep(2 ** (attempt - 1))
    raise AIProviderError("all", "All AI providers failed: " + "; ".join(failures))


def run_validated(
    db: Session,
    system_prompt: str,
    user_prompt: str,
    validate: Callable[[AIResult], Any],
    json_mode: bool = True,
    product_id: Optional[int] = None,
    call_type: str = "other",
) -> tuple[AIResult, Any]:
    """Like ``run_with_fallback`` but validates the reply inside the retry loop.

    A response that parses/validates incorrectly is treated like a provider
    failure: the call is retried (with a JSON nudge) and then falls back to the
    next provider. Returns the raw result plus the validated payload so callers
    keep provider/model provenance.
    """
    settings = get_settings()
    chain = get_provider_chain()
    max_retries = max(1, settings.AI_MAX_RETRIES)
    combined = _combined_prompt(system_prompt, user_prompt)
    failures: list[str] = []
    for provider in chain:
        prompt = user_prompt
        for attempt in range(1, max_retries + 1):
            try:
                result = provider.complete(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    temperature=settings.AI_TEMPERATURE,
                    max_tokens=settings.AI_MAX_TOKENS,
                    json_mode=json_mode,
                )
            except AIAuthError as exc:
                _safe_record(
                    db, product_id, combined, f"ERROR: {exc}", provider.name,
                    provider.model, None, False, call_type=call_type,
                )
                failures.append(f"{provider.name} auth failed: {exc}")
                logger.warning("AI auth failed, skipping retries: %s", exc)
                break
            except (AIRateLimitError, AIProviderError) as exc:
                _safe_record(
                    db, product_id, combined, f"ERROR: {exc}", provider.name,
                    provider.model, None, False, call_type=call_type,
                )
                failures.append(
                    f"{provider.name} attempt {attempt}/{max_retries}: {exc}"
                )
                logger.warning("AI attempt failed: %s", exc)
                if attempt < max_retries and not settings.AI_MOCK_MODE:
                    time.sleep(2 ** (attempt - 1))
                continue
            try:
                payload = validate(result)
            except AIResponseParseError as exc:
                _safe_record(
                    db, product_id, combined, result.text, provider.name,
                    provider.model, result.tokens_used, False, call_type=call_type,
                )
                failures.append(f"{provider.name} invalid response: {exc}")
                logger.warning("AI response failed validation: %s", exc)
                prompt = user_prompt + "\n\n" + _RETRY_NOTE
                if attempt < max_retries and not settings.AI_MOCK_MODE:
                    time.sleep(2 ** (attempt - 1))
                continue
            _safe_record(
                db, product_id, combined, result.text, provider.name,
                provider.model, result.tokens_used, True, call_type=call_type,
            )
            return result, payload
    raise AIProviderError("all", "All AI providers failed: " + "; ".join(failures))
