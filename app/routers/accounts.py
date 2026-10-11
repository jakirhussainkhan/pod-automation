"""Multi-account ghost-profile API router (Phase 5)."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.routers.deps import require_destructive_confirmation
from app.services import account_service, dm_safety
from app.services.account_service import EDITABLE_ACCOUNT_FIELDS

logger = logging.getLogger("pod-automation")

router: APIRouter = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    """Create a ghost-profile account (name required, rest optional)."""

    name: str = Field(min_length=1, max_length=120)
    handle: Optional[str] = Field(default=None, max_length=60)
    profile_url: Optional[str] = Field(default=None, max_length=500)
    persona_name: Optional[str] = Field(default=None, max_length=120)
    persona_avatar_url: Optional[str] = Field(default=None, max_length=500)
    persona_bio: Optional[str] = Field(default=None, max_length=2000)
    persona_tone: Optional[str] = Field(default=None, max_length=20)
    niche_focus: Optional[str] = Field(default=None, max_length=20)
    daily_limit: Optional[int] = Field(default=None, ge=1, le=100)
    hourly_limit: Optional[int] = Field(default=None, ge=1, le=100)
    priority: Optional[int] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class AccountUpdate(BaseModel):
    """Partial account update; every field optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    handle: Optional[str] = Field(default=None, max_length=60)
    profile_url: Optional[str] = Field(default=None, max_length=500)
    persona_name: Optional[str] = Field(default=None, max_length=120)
    persona_avatar_url: Optional[str] = Field(default=None, max_length=500)
    persona_bio: Optional[str] = Field(default=None, max_length=2000)
    persona_tone: Optional[str] = Field(default=None, max_length=20)
    niche_focus: Optional[str] = Field(default=None, max_length=20)
    daily_limit: Optional[int] = Field(default=None, ge=1, le=100)
    hourly_limit: Optional[int] = Field(default=None, ge=1, le=100)
    priority: Optional[int] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    is_active: Optional[bool] = None
    health_status: Optional[str] = Field(default=None, max_length=20)
    health_note: Optional[str] = Field(default=None, max_length=500)


class AccountNote(BaseModel):
    """Free-text note for warning/ban events."""

    note: str = Field(min_length=1, max_length=500)


class BlockGroupRequest(BaseModel):
    """Block an account from posting in one group."""

    group_name: str = Field(min_length=1, max_length=200)
    reason: Optional[str] = Field(default="manual", max_length=20)


class BulkAssignRequest(BaseModel):
    """Backfill orphan leads; optional id scope (default: all NULLs)."""

    ids: Optional[list[int]] = Field(default=None, max_length=500)


@router.get("", summary="List Facebook accounts with health + usage", description="All ghost-profile accounts with live quota usage, health and lifetime conversion rollup in one query.")
def list_accounts(
    include_inactive: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    """List accounts newest-priority-first with computed fields."""
    items = account_service.list_accounts(db, include_inactive=include_inactive, window_days=30)
    return {"items": items, "total": len(items)}


@router.post("", status_code=201, summary="Create a new FB account persona", description="Validates name/handle/tone/niche/limits, defaults to healthy priority 100.")
def create_account(data: AccountCreate, db: Session = Depends(get_db)) -> dict:
    """Create an account."""
    try:
        account = account_service.create_account(db, data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    items = [a for a in account_service.list_accounts(db) if a["id"] == account.id]
    return items[0]


@router.get("/{account_id}", summary="Get account detail + 30d stats", description="Single account with computed usage plus trailing-30-day funnel stats.")
def get_account(account_id: int, db: Session = Depends(get_db)) -> dict:
    """Fetch one account with stats."""
    items = [a for a in account_service.list_accounts(db) if a["id"] == account_id]
    if not items:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found.")
    try:
        stats = account_service.get_account_stats(db, account_id, 30)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"account": items[0], "stats": stats}


@router.patch("/{account_id}", summary="Update account persona / limits / status", description="Partial update with the same validation as create (tone/niche enums, limits 1..100, unique handle).")
def update_account(account_id: int, data: AccountUpdate, db: Session = Depends(get_db)) -> dict:
    """Update an account."""
    payload = {k: v for k, v in data.model_dump(exclude_unset=True).items()
               if k in EDITABLE_ACCOUNT_FIELDS}
    try:
        account = account_service.update_account(db, account_id, payload)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=422, detail=message)
    items = [a for a in account_service.list_accounts(db) if a["id"] == account.id]
    return items[0]


@router.delete("/{account_id}", status_code=204, summary="Delete account (snapshot saved for restore)", description="Detaches assigned leads, refuses the last active account with 409, logs a restorable snapshot. Requires X-Confirm-Delete.")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> None:
    """Delete an account."""
    try:
        account_service.delete_account(db, account_id)
    except ValueError as exc:
        message = str(exc)
        if "last account" in message:
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=404, detail=message)
    return None


@router.post("/{account_id}/warning", summary="Log FB warning against account", description="Increments warnings, marks warned, auto-pauses for warning_pause_hours when configured.")
def account_warning(account_id: int, data: AccountNote, db: Session = Depends(get_db)) -> dict:
    """Record a warning."""
    try:
        account = dm_safety.record_account_warning(account_id, data.note, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    items = [a for a in account_service.list_accounts(db) if a["id"] == account.id]
    return items[0]


@router.post("/{account_id}/ban", summary="Log FB ban (auto-pauses for recovery period)", description="Marks banned with restricted_until = now + ban_recovery_days.")
def account_ban(account_id: int, data: AccountNote, db: Session = Depends(get_db)) -> dict:
    """Record a ban."""
    try:
        account = dm_safety.record_account_ban(account_id, data.note, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    items = [a for a in account_service.list_accounts(db) if a["id"] == account.id]
    return items[0]


@router.post("/{account_id}/restore", summary="Mark account healthy again", description="Clears restriction + note; warnings_count is kept as permanent history.")
def account_restore(account_id: int, db: Session = Depends(get_db)) -> dict:
    """Restore an account to healthy."""
    try:
        account = dm_safety.record_account_restore(account_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    items = [a for a in account_service.list_accounts(db) if a["id"] == account.id]
    return items[0]


@router.post("/{account_id}/block-group", summary="Manually block account from a group", description="Insert-or-ignore collision entry for one account/group pair.")
def block_group(account_id: int, data: BlockGroupRequest, db: Session = Depends(get_db)) -> dict:
    """Block an account from a group."""
    from app.models.fb_account import FbAccount

    if db.get(FbAccount, account_id) is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found.")
    dm_safety.block_account_from_group(account_id, data.group_name, data.reason or "manual", db)
    return {"account_id": account_id, "group_name": data.group_name.strip(),
            "blocked": dm_safety.is_account_blocked_from_group(account_id, data.group_name, db)}


@router.get("/{account_id}/performance", summary="Per-account performance", description="Windowed funnel stats (dms, converted, revenue, rate, daily average). Max 3 queries.")
def account_performance(
    account_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """Return performance stats."""
    try:
        return account_service.get_account_stats(db, account_id, days)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/auto-assign-orphans", summary="Backfill orphan leads to accounts", description="Assigns NULL-assigned leads via rotation (optional id scope). Returns assigned/skipped counts.")
def auto_assign_orphans(data: BulkAssignRequest | None, db: Session = Depends(get_db)) -> dict:
    """Assign orphan leads to best-fit accounts."""
    from app.models.group_lead import GroupLead

    query = db.query(GroupLead).filter(GroupLead.assigned_account_id.is_(None))
    scope = data.ids if (data and data.ids) else None
    if scope:
        query = query.filter(GroupLead.id.in_(scope))
    orphans = query.order_by(GroupLead.id.asc()).all()
    assigned = 0
    skipped = 0
    for lead in orphans:
        try:
            pick = dm_safety.get_next_available_account(db, lead)
            if pick is None:
                skipped += 1
                continue
            lead.assigned_account_id = pick.id
            db.commit()
            assigned += 1
        except Exception:
            db.rollback()
            logger.exception("Orphan assign failed for lead %s.", lead.id)
            skipped += 1
    return {"assigned": assigned, "skipped": skipped}
