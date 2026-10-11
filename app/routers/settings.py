"""Public settings API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import WIPE_CONFIRM_TEXT
from app.database.session import get_db
from app.routers.deps import require_destructive_confirmation
from app.services import maintenance_service, settings_service
from app.services.settings_service import EDITABLE_SETTING_KEYS

router: APIRouter = APIRouter(prefix="/api/settings", tags=["settings"])


class ClearDummyDataRequest(BaseModel):
    """Confirmation payload for dummy-data cleanup.

    Default (no flags) removes only ``is_demo`` rows. Passing
    ``wipe_all=True`` together with ``confirmation == "WIPE ALL DATA"``
    performs a full wipe of products/posts/leads/queue.
    """

    wipe_all: bool = False
    confirmation: Optional[str] = None

SettingsUpdateRequest = dict[str, str]
"""Request body type: a dict of setting key to string value."""


@router.get("", response_model=dict[str, str])
def get_settings_endpoint(db: Session = Depends(get_db)) -> dict[str, str]:
    """Return whitelisted public settings with defaults."""
    return settings_service.get_public_settings(db)


@router.put("", response_model=dict[str, str])
def update_settings_endpoint(
    payload: SettingsUpdateRequest, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Update whitelisted settings after validating keys and values."""
    allowed = sorted(EDITABLE_SETTING_KEYS)
    invalid = [key for key in payload if key not in EDITABLE_SETTING_KEYS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid setting keys: {', '.join(sorted(invalid))}. "
            f"Allowed keys: {', '.join(allowed)}.",
        )
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        try:
            normalized[key] = settings_service.validate_setting_value(key, value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    # All values validated before any write: no partial updates on failure.
    try:
        for key, value in normalized.items():
            settings_service.set_setting_checked(db, key, value)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        db.rollback()
        raise
    return settings_service.get_public_settings(db)


@router.post("/clear-dummy-data", response_model=dict)
def clear_dummy_data_endpoint(
    payload: ClearDummyDataRequest | None = None,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> dict:
    """Remove demo rows (``is_demo=True``) or, with explicit confirmation, wipe all.

    Safe mode (default) purges only seeded demo rows and leaves real
    leads, posts, and revenue records intact. Full wipes require
    ``{"wipe_all": true, "confirmation": "WIPE ALL DATA"}`` plus the
    ``X-Confirm-Delete`` header.
    """
    wipe_all = bool(payload and payload.wipe_all)
    confirmation = (payload.confirmation if payload else None) or ""
    if wipe_all and confirmation != WIPE_CONFIRM_TEXT:
        raise HTTPException(
            status_code=422,
            detail=f'Full wipe requires confirmation="{WIPE_CONFIRM_TEXT}".',
        )
    return maintenance_service.clear_dummy_data(db, wipe_all=wipe_all)
