"""Multi-account CRUD + per-account analytics (Phase 5 ghost profiles)."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.fb_account import (
    ACCOUNT_HEALTH_VALUES,
    NICHE_FOCUS_VALUES,
    PERSONA_TONES,
    FbAccount,
)
from app.models.group_lead import GroupLead

logger = logging.getLogger("pod-automation")

EDITABLE_ACCOUNT_FIELDS: tuple[str, ...] = (
    "name", "handle", "profile_url", "persona_name", "persona_avatar_url",
    "persona_bio", "persona_tone", "niche_focus", "daily_limit",
    "hourly_limit", "priority", "notes", "is_active", "health_status",
    "health_note",
)
"""Fields accepted on create/update (counters/dates are system-owned)."""


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _clean_handle(value: Optional[str]) -> Optional[str]:
    """Normalize an @handle (strip @/spaces) or return None when blank."""
    text = (value or "").strip().lstrip("@").strip()
    return text[:60] if text else None


def validate_account_payload(payload: dict, partial: bool = False) -> dict:
    """Validate + normalize account fields; raise ValueError on violation."""
    data = dict(payload or {})
    cleaned: dict = {}
    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Account name is required.")
        cleaned["name"] = name[:120]
    for key in ("profile_url", "persona_avatar_url"):
        if key in data:
            value = data[key]
            cleaned[key] = str(value).strip()[:500] or None if value is not None else None
    for key in ("persona_name",):
        if key in data:
            value = data[key]
            cleaned[key] = str(value).strip()[:120] or None if value is not None else None
    for key in ("persona_bio", "notes"):
        if key in data:
            value = data[key]
            cleaned[key] = str(value).strip() or None if value is not None else None
    if "health_note" in data:
        value = data["health_note"]
        cleaned["health_note"] = str(value).strip()[:500] or None if value is not None else None
    if "handle" in data:
        cleaned["handle"] = _clean_handle(data["handle"])
    if "persona_tone" in data:
        tone = data["persona_tone"]
        if tone is None or str(tone).strip() == "":
            cleaned["persona_tone"] = None
        else:
            lowered = str(tone).strip().lower()
            if lowered not in PERSONA_TONES:
                raise ValueError(
                    f"Invalid persona_tone {tone!r}. Allowed: {', '.join(PERSONA_TONES)}."
                )
            cleaned["persona_tone"] = lowered
    if "niche_focus" in data:
        niche = data["niche_focus"]
        if niche is None or str(niche).strip() == "":
            cleaned["niche_focus"] = None
        else:
            lowered = str(niche).strip().lower()
            if lowered not in NICHE_FOCUS_VALUES:
                raise ValueError(
                    f"Invalid niche_focus {niche!r}. Allowed: {', '.join(NICHE_FOCUS_VALUES)}."
                )
            cleaned["niche_focus"] = lowered
    if "health_status" in data:
        status = str(data["health_status"] or "").strip().lower()
        if status not in ACCOUNT_HEALTH_VALUES:
            raise ValueError(
                f"Invalid health_status {data['health_status']!r}. "
                f"Allowed: {', '.join(ACCOUNT_HEALTH_VALUES)}."
            )
        cleaned["health_status"] = status
    for key in ("daily_limit", "hourly_limit"):
        if key in data:
            try:
                number = int(data[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be an integer between 1 and 100.")
            if not 1 <= number <= 100:
                raise ValueError(f"{key} must be an integer between 1 and 100.")
            cleaned[key] = number
    if "priority" in data:
        try:
            number = int(data["priority"])
        except (TypeError, ValueError):
            raise ValueError("priority must be an integer.")
        cleaned["priority"] = number
    if "is_active" in data:
        value = data["is_active"]
        if isinstance(value, bool):
            cleaned["is_active"] = value
        elif str(value).strip().lower() in ("true", "1", "yes"):
            cleaned["is_active"] = True
        elif str(value).strip().lower() in ("false", "0", "no"):
            cleaned["is_active"] = False
        else:
            raise ValueError('is_active must be a boolean ("true"/"false").')
    return cleaned


def _check_handle_unique(db: Session, handle: Optional[str], ignore_id: Optional[int] = None) -> None:
    """Raise ValueError when another account already owns the handle."""
    if not handle:
        return
    query = db.query(FbAccount).filter(func.lower(FbAccount.handle) == handle.lower())
    if ignore_id is not None:
        query = query.filter(FbAccount.id != ignore_id)
    if query.first() is not None:
        raise ValueError(f"Handle {handle!r} is already taken by another account.")


def create_account(db: Session, payload: dict) -> FbAccount:
    """Create an account persona after validation (healthy, priority 100)."""
    from app.services import log_service

    cleaned = validate_account_payload(payload, partial=False)
    _check_handle_unique(db, cleaned.get("handle"))
    try:
        # Explicit payload wins; model column defaults cover the rest.
        cleaned.setdefault("health_status", "healthy")
        cleaned.setdefault("priority", 100)
        account = FbAccount(**cleaned)
        db.add(account)
        db.commit()
        db.refresh(account)
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Account create hit a constraint.")
        raise ValueError(f"Account could not be saved (possible duplicate handle): {exc}")
    except Exception:
        db.rollback()
        logger.exception("Account create failed.")
        raise
    try:
        log_service.add_log(
            db, "account_created", f"Account {account.id} ({account.name}) created.",
            entity_type="fb_account", entity_id=account.id,
        )
    except Exception:
        logger.exception("Account-created log failed (non-fatal).")
    return account


def update_account(db: Session, account_id: int, payload: dict) -> FbAccount:
    """Partially update an account persona after validation."""
    from app.services import log_service

    account = db.get(FbAccount, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found.")
    cleaned = validate_account_payload(payload, partial=True)
    if "handle" in cleaned:
        _check_handle_unique(db, cleaned["handle"], ignore_id=account_id)
    try:
        for key, value in cleaned.items():
            setattr(account, key, value)
        db.commit()
        db.refresh(account)
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Account update hit a constraint.")
        raise ValueError(f"Account could not be saved (possible duplicate handle): {exc}")
    except Exception:
        db.rollback()
        logger.exception("Account update failed for %s.", account_id)
        raise
    try:
        log_service.add_log(
            db, "account_updated", f"Account {account.id} ({account.name}) updated.",
            entity_type="fb_account", entity_id=account.id,
        )
    except Exception:
        logger.exception("Account-updated log failed (non-fatal).")
    return account


def delete_account(db: Session, account_id: int) -> dict:
    """Delete an account, refusing the last active one (409 upstream).

    Assigned leads are detached (assigned_account_id → NULL) so no
    orphan FK survives. A snapshot is logged for restore.
    """
    from app.services import log_service

    account = db.get(FbAccount, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found.")
    remaining = (
        db.query(func.count(FbAccount.id))
        .filter(FbAccount.is_active.is_(True), FbAccount.id != account_id)
        .scalar()
        or 0
    )
    if bool(getattr(account, "is_active", False)) and int(remaining) == 0:
        raise ValueError("Cannot delete last account.")
    snapshot = {
        "id": account.id,
        "name": account.name,
        "handle": account.handle,
        "persona_name": account.persona_name,
        "persona_tone": account.persona_tone,
        "niche_focus": account.niche_focus,
        "daily_limit": account.daily_limit,
        "hourly_limit": account.hourly_limit,
        "priority": account.priority,
        "health_status": account.health_status,
    }
    try:
        db.query(GroupLead).filter(
            GroupLead.assigned_account_id == account_id
        ).update({GroupLead.assigned_account_id: None}, synchronize_session=False)
        db.delete(account)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Account delete failed for %s.", account_id)
        raise
    try:
        log_service.add_log(
            db, "account_deleted",
            f"Account {account_id} ({snapshot.get('name')}) deleted; leads detached.",
            snapshot={"fb_account": snapshot},
            entity_type="fb_account", entity_id=account_id,
        )
    except Exception:
        logger.exception("Account-deleted log failed (non-fatal).")
    return snapshot


def _account_to_dict(account: FbAccount, usage: Optional[dict] = None) -> dict:
    """Serialize an account plus computed usage/health fields."""
    usage = usage or {}
    restricted = getattr(account, "restricted_until", None)
    if restricted is not None and getattr(restricted, "tzinfo", None) is None:
        from datetime import timezone as _tz

        restricted = restricted.replace(tzinfo=_tz.utc)
    last_active = getattr(account, "last_active_at", None)
    captured = int(usage.get("leads", 0) or 0)
    converted = int(usage.get("converted", 0) or 0)
    return {
        "id": account.id,
        "name": account.name,
        "handle": account.handle,
        "profile_url": account.profile_url,
        "persona_name": account.persona_name,
        "persona_avatar_url": account.persona_avatar_url,
        "persona_bio": account.persona_bio,
        "persona_tone": account.persona_tone,
        "niche_focus": account.niche_focus,
        "health_status": account.health_status,
        "health_note": account.health_note,
        "restricted_until": restricted.isoformat() if restricted else None,
        "warnings_count": int(account.warnings_count or 0),
        "total_dms_sent": int(account.total_dms_sent or 0),
        "total_converted": int(account.total_converted or 0),
        "total_revenue": round(float(account.total_revenue or 0.0), 2),
        "last_active_at": last_active.isoformat() if last_active else None,
        "priority": int(account.priority if account.priority is not None else 100),
        "notes": account.notes,
        "daily_limit": int(account.daily_limit or 20),
        "hourly_limit": int(account.hourly_limit or 10),
        "hourly_used": int(usage.get("hourly_used", account.hourly_dm_count or 0)),
        "daily_used": int(usage.get("daily_used", account.daily_dm_count or 0)),
        "is_active": bool(account.is_active),
        "dm_conversion_rate": round(converted / captured, 4) if captured else 0.0,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


def list_accounts(
    db: Session, include_inactive: bool = True, window_days: Optional[int] = None
) -> list[dict]:
    """List accounts with live usage + conversion rollup in ONE query.

    ``window_days`` adds trailing-window funnel fields (d30_leads,
    d30_converted, d30_revenue) via conditional sums — still one query.
    """
    from datetime import timedelta as _td
    from sqlalchemy import case

    cutoff = None
    if window_days is not None:
        try:
            cutoff = _utcnow() - _td(days=max(1, min(365, int(window_days))))
        except (TypeError, ValueError):
            cutoff = None

    def _in_window():
        return True if cutoff is None else (GroupLead.created_at >= cutoff)

    query = (
        db.query(
            FbAccount,
            func.count(GroupLead.id).label("leads"),
            func.coalesce(
                func.sum(case((GroupLead.status == "converted", 1), else_=0)), 0
            ).label("converted"),
            func.coalesce(
                func.sum(case((_in_window(), 1), else_=0)), 0
            ).label("w_leads"),
            func.coalesce(
                func.sum(case(
                    ((GroupLead.status == "converted") & _in_window(), 1), else_=0,
                )), 0,
            ).label("w_converted"),
            func.coalesce(
                func.sum(case(
                    ((GroupLead.status == "converted") & _in_window(),
                     GroupLead.conversion_value),
                    else_=0.0,
                )), 0.0,
            ).label("w_revenue"),
        )
        .outerjoin(GroupLead, GroupLead.assigned_account_id == FbAccount.id)
        .group_by(FbAccount.id)
        .order_by(FbAccount.priority.asc(), FbAccount.id.asc())
    )
    if not include_inactive:
        query = query.filter(FbAccount.is_active.is_(True))
    result = []
    for account, leads, converted, w_leads, w_converted, w_revenue in query.all():
        usage = {
            "leads": leads, "converted": converted,
            "hourly_used": account.hourly_dm_count,
            "daily_used": account.daily_dm_count,
        }
        card = _account_to_dict(account, usage)
        card["d30_leads"] = int(w_leads or 0)
        card["d30_converted"] = int(w_converted or 0)
        card["d30_revenue"] = round(float(w_revenue or 0.0), 2)
        card["d30_rate"] = (
            round(card["d30_converted"] / card["d30_leads"], 4) if card["d30_leads"] else 0.0
        )
        result.append(card)
    return result


def get_account_stats(db: Session, account_id: int, days: int = 30) -> dict:
    """Windowed funnel stats for one account (2 queries: row + aggregate)."""
    window = max(1, min(365, int(days)))
    cutoff = _utcnow() - timedelta(days=window)
    account = db.get(FbAccount, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found.")
    from sqlalchemy import case, or_

    agg = (
        db.query(
            func.count(GroupLead.id).label("captured"),
            func.sum(
                case(
                    (
                        or_(
                            GroupLead.step1_sent_at >= cutoff,
                            GroupLead.step2_sent_at >= cutoff,
                            GroupLead.follow_up_sent_at >= cutoff,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("dms"),
            func.sum(
                case((GroupLead.status == "converted", 1), else_=0)
            ).label("converted"),
            func.coalesce(
                func.sum(
                    case(
                        (GroupLead.status == "converted", GroupLead.conversion_value),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("revenue"),
        )
        .filter(
            GroupLead.assigned_account_id == account_id,
            GroupLead.created_at >= cutoff,
        )
        .one()
    )
    captured = int(agg.captured or 0)
    converted = int(agg.converted or 0)
    dms = int(agg.dms or 0)
    revenue = round(float(agg.revenue or 0.0), 2)
    last_active = getattr(account, "last_active_at", None)
    return {
        "account_id": account_id,
        "days": window,
        "dms_sent": dms,
        "converted": converted,
        "revenue": revenue,
        "conversion_rate": round(converted / captured, 4) if captured else 0.0,
        "avg_per_day": round(dms / window, 2),
        "last_active_at": last_active.isoformat() if last_active else None,
    }
