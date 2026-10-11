"""Facebook connection API router."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.facebook import FacebookStatus
from app.services import settings_service
from app.services.facebook.status import get_facebook_status

router: APIRouter = APIRouter(prefix="/api/facebook", tags=["facebook"])

logger = logging.getLogger("pod-automation")


@router.get("/status", response_model=FacebookStatus)
async def facebook_status_endpoint() -> FacebookStatus:
    """Return Facebook configuration and token validity (no secrets)."""
    try:
        return FacebookStatus(**await get_facebook_status())
    except Exception as exc:
        logger.exception("Facebook status endpoint failed.")
        raise HTTPException(status_code=502, detail="Facebook status check failed.")


@router.post("/test-connection", response_model=FacebookStatus)
async def facebook_test_connection_endpoint(db: Session = Depends(get_db)) -> FacebookStatus:
    """Force a fresh token verification and return the status.

    On a valid token, stamps ``token_added_at``/``token_expires_at``
    (+60 days) so expiry warnings stay accurate. Failures never
    overwrite existing dates.
    """
    try:
        # No cache layer exists today, so test-connection always verifies live.
        status = FacebookStatus(**await get_facebook_status())
    except Exception as exc:
        logger.exception("Facebook test-connection endpoint failed.")
        raise HTTPException(status_code=502, detail="Facebook verification failed.")
    if status.token_valid:
        try:
            now = datetime.now(timezone.utc)
            settings_service.set_setting(db, "token_added_at", now.isoformat())
            settings_service.set_setting(
                db, "token_expires_at", (now + timedelta(days=60)).isoformat()
            )
        except Exception:
            logger.exception("Failed to stamp token dates.")
    return status
