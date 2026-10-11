"""System operations router: health, backups, AI usage, token, kill switch."""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.routers.deps import require_destructive_confirmation
from app.services import (
    ai_usage_service,
    backup_service,
    health_service,
    settings_service,
)

logger = logging.getLogger("pod-automation")

router: APIRouter = APIRouter(prefix="/api/system", tags=["system"])

_RESTORE_CONFIRM_TEXT = "RESTORE BACKUP"
"""Exact confirmation string required for backup restores."""

_health_cache: dict = {"at": 0.0, "payload": None}
_HEALTH_TTL_SECONDS = 30.0


def bust_health_cache() -> None:
    """Invalidate the health snapshot (call after kill/token changes)."""
    _health_cache["at"] = 0.0
    _health_cache["payload"] = None

_last_manual_backup_at: float = 0.0
_last_restore_at: float = 0.0


class KillSwitchRequest(BaseModel):
    """Emergency-stop toggle payload."""

    active: bool


class RestoreRequest(BaseModel):
    """Restore confirmation payload (typed confirmation string)."""

    confirmation: str = Field(min_length=1, max_length=64)


def _rate_limited(last: float, window: float) -> bool:
    """True when a call happened inside the cooldown window."""
    return (time.monotonic() - last) < window


@router.get("/health", summary="System health snapshot", description="DB, Facebook, AI, queue, kill-switch, backup and disk checks in one payload. Cached 30s so dashboard polls never hammer live APIs.")
async def system_health(db: Session = Depends(get_db)) -> dict:
    """Return the cached-or-fresh system health snapshot."""
    now = time.monotonic()
    if _health_cache["payload"] is not None and (now - _health_cache["at"]) < _HEALTH_TTL_SECONDS:
        return _health_cache["payload"]
    payload = await health_service.get_system_health(db)
    _health_cache["at"] = now
    _health_cache["payload"] = payload
    return payload


@router.get("/backups", summary="List DB backups", description="Newest-first backup rows with on-disk existence flags.")
def list_backups(db: Session = Depends(get_db)) -> dict:
    """List recorded backups."""
    items = backup_service.list_backups(db)
    return {"items": items, "total": len(items)}


@router.post("/backups/run", summary="Run manual DB backup", description="Snapshot the live SQLite file atomically and prune beyond retention. Rate-limited to one run per 60 seconds.")
def run_backup(db: Session = Depends(get_db)) -> dict:
    """Trigger a manual backup (1 per 60s)."""
    global _last_manual_backup_at
    if _rate_limited(_last_manual_backup_at, 60.0):
        raise HTTPException(status_code=429, detail="Backup already ran recently — wait a minute.")
    try:
        result = backup_service.run_backup(db, trigger="manual")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _last_manual_backup_at = time.monotonic()
    return result


@router.get("/backups/{backup_id}/download", summary="Download a DB backup", description="Stream the backup SQLite file with an attachment disposition.")
def download_backup(backup_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Download a backup file."""
    from app.models.system import DbBackup

    row = db.get(DbBackup, backup_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Backup {backup_id} not found.")
    if not Path(row.file_path).exists():
        raise HTTPException(status_code=404, detail="Backup file is missing from disk.")
    return FileResponse(
        path=row.file_path,
        filename=row.filename,
        media_type="application/x-sqlite3",
    )


@router.delete("/backups/{backup_id}", status_code=204, summary="Delete a DB backup", description="Remove the backup file and its row. Requires the X-Confirm-Delete header.")
def delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> None:
    """Delete a backup."""
    try:
        backup_service.delete_backup(db, backup_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return None


@router.post("/backups/{backup_id}/restore", summary="Restore from backup (requires restart)", description="Snapshot a pre-restore backup first, then copy the backup over the live DB. Requires the typed RESTORE BACKUP confirmation plus the X-Confirm-Delete header. Never auto-restarts.")
def restore_backup(
    backup_id: int,
    data: RestoreRequest,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> dict:
    """Restore a backup (1 per 10 min)."""
    global _last_restore_at
    if (data.confirmation or "").strip() != _RESTORE_CONFIRM_TEXT:
        raise HTTPException(
            status_code=422,
            detail=f'Restore requires confirmation="{_RESTORE_CONFIRM_TEXT}".',
        )
    if _rate_limited(_last_restore_at, 600.0):
        raise HTTPException(status_code=429, detail="Restore ran recently — wait 10 minutes.")
    try:
        result = backup_service.restore_backup(backup_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _last_restore_at = time.monotonic()
    return result


@router.get("/ai-usage", summary="AI usage + cost summary", description="Per-provider totals, per-day series, window totals and month-to-date cost. Two queries max.")
def ai_usage(
    days: int = 30,
    db: Session = Depends(get_db),
) -> dict:
    """Return the AI usage rollup."""
    if not 1 <= int(days) <= 365:
        raise HTTPException(status_code=422, detail="days must be between 1 and 365.")
    return ai_usage_service.get_usage_summary(db, days)


@router.get("/token-status", summary="Facebook token expiry status", description="Token presence, stamp dates, days left and the ok/soon/urgent/expired warning level.")
def token_status(db: Session = Depends(get_db)) -> dict:
    """Return the token expiry state."""
    return health_service.token_status(db)


@router.post("/token-refresh-note", summary="Stamp a refreshed token", description="Record now as the token refresh moment (expiry = +60 days). Use after pasting a fresh token into .env.")
def token_refresh_note(db: Session = Depends(get_db)) -> dict:
    """Stamp token_added_at/expires_at from now."""
    now = datetime.now(timezone.utc)
    settings_service.set_setting(db, "token_added_at", now.isoformat())
    from datetime import timedelta

    settings_service.set_setting(
        db, "token_expires_at", (now + timedelta(days=60)).isoformat()
    )
    bust_health_cache()
    return health_service.token_status(db)


@router.post("/kill-switch", summary="Emergency stop — blocks all posting", description="Engage or release the kill switch. Engaging requires the X-Confirm-Delete header; both layers (scheduler + publisher) enforce it.")
def kill_switch(
    data: KillSwitchRequest,
    db: Session = Depends(get_db),
    x_confirm_delete: Optional[str] = Header(default=None, alias="X-Confirm-Delete"),
) -> dict:
    """Toggle the emergency stop."""
    # Only *engaging* the switch needs the destructive confirmation, so
    # the header is validated inline (same accepted values as deps.py)
    # instead of through the always-require dependency.
    if data.active and (x_confirm_delete or "").strip().lower() not in {
        "1", "true", "yes", "confirm",
    }:
        raise HTTPException(
            status_code=403,
            detail="Destructive action requires X-Confirm-Delete header.",
        )
    settings_service.set_kill_switch(db, bool(data.active))
    bust_health_cache()
    return {"kill_switch_active": bool(data.active)}
