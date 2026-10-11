"""Facebook connection status reporting."""

import logging
from typing import Optional

from app.config import get_settings
from app.services.facebook.client import FacebookClient
from app.services.facebook.exceptions import FacebookError, redact_token_text

logger = logging.getLogger("pod-automation")


def mask_page_id(page_id: str) -> Optional[str]:
    """Mask a Page id, showing only the last 4 characters."""
    value = (page_id or "").strip()
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return "***" + value[-4:]


async def get_facebook_status() -> dict:
    """Report Facebook configuration, dry-run mode and token validity."""
    settings = get_settings()
    configured = settings.has_facebook_credentials()
    dry_run = settings.FACEBOOK_DRY_RUN
    masked = mask_page_id(settings.FACEBOOK_PAGE_ID)
    if not configured and not dry_run:
        return {
            "configured": False,
            "dry_run": dry_run,
            "page_id": masked,
            "page_name": None,
            "token_valid": None,
            "error": "Facebook credentials are not configured.",
        }
    try:
        client = FacebookClient()
    except Exception as exc:
        safe = redact_token_text(str(exc)) or "Facebook client init failed."
        logger.warning("Facebook status check failed: %s", safe)
        return {
            "configured": configured,
            "dry_run": dry_run,
            "page_id": masked,
            "page_name": None,
            "token_valid": False,
            "error": safe,
        }
    try:
        info = await client.verify_token()
    except FacebookError as exc:
        safe = redact_token_text(str(exc)) or "Facebook verification failed."
        logger.warning("Facebook status check failed: %s", safe)
        return {
            "configured": configured,
            "dry_run": dry_run,
            "page_id": masked,
            "page_name": None,
            "token_valid": False,
            "error": safe,
        }
    except Exception as exc:
        safe = redact_token_text(str(exc)) or "Facebook verification failed."
        logger.warning("Facebook status check failed: %s", safe)
        return {
            "configured": configured,
            "dry_run": dry_run,
            "page_id": masked,
            "page_name": None,
            "token_valid": False,
            "error": safe,
        }
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
    return {
        "configured": configured,
        "dry_run": dry_run,
        "page_id": masked,
        "page_name": info.get("page_name"),
        "token_valid": True,
        "error": None,
    }
