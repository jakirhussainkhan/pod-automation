"""Lead lifecycle: reply-check reminders + cold-lead follow-up engine (Phase 2)."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.group_lead import GroupLead
from app.services.dm_safety import _ensure_aware, _get_int_setting, get_cold_lead_days

logger = logging.getLogger("pod-automation")

REPLY_STATES: tuple[str, ...] = ("unknown", "replied", "no_reply", "bounced")

_M2_DONE_STATUSES: frozenset[str] = frozenset({"step2_sent", "converted"})


def get_reply_check_delay_hours(db: Optional[Session] = None) -> int:
    """First reply-check reminder threshold in hours (default 6)."""
    return max(1, min(168, _get_int_setting(db, "reply_check_delay_hours", 6)))


def get_reply_check_second_hours(db: Optional[Session] = None) -> int:
    """Overdue reply-check threshold in hours (default 24)."""
    return max(1, min(168, _get_int_setting(db, "reply_check_second_hours", 24)))


def is_follow_up_enabled(db: Optional[Session] = None) -> bool:
    """Return True unless the follow-up engine was disabled in settings."""
    if db is None:
        return True
    try:
        from app.services import settings_service

        raw = settings_service.get_setting(db, "follow_up_enabled", "true")
        return str(raw).strip().lower() != "false"
    except Exception:
        logger.exception("Failed to read follow_up_enabled; assuming enabled.")
        return True


def get_max_follow_ups(db: Optional[Session] = None) -> int:
    """Maximum follow-ups per lead (default 1)."""
    return max(1, min(5, _get_int_setting(db, "max_follow_ups", 1)))


def _lifecycle_cfg(db: Optional[Session]) -> dict:
    """Read all lifecycle thresholds once (avoids per-lead setting queries)."""
    return {
        "delay_hours": get_reply_check_delay_hours(db),
        "second_hours": get_reply_check_second_hours(db),
        "cold_days": get_cold_lead_days(db),
        "follow_up_enabled": is_follow_up_enabled(db),
        "max_follow_ups": get_max_follow_ups(db),
    }


def _age_hours(lead: GroupLead, now: datetime) -> Optional[float]:
    """Hours since M1 was sent, or None when M1 was never sent."""
    sent_at = _ensure_aware(getattr(lead, "step1_sent_at", None))
    if sent_at is None:
        return None
    return max(0.0, (now - sent_at).total_seconds() / 3600.0)


def _m2_sent(lead: GroupLead) -> bool:
    """True once Message 2 has gone out (or the lead converted)."""
    if _ensure_aware(getattr(lead, "step2_sent_at", None)) is not None:
        return True
    return (getattr(lead, "status", "") or "") in _M2_DONE_STATUSES


def compute_lead_urgency(
    lead: GroupLead,
    now: Optional[datetime] = None,
    cfg: Optional[dict] = None,
    db: Optional[Session] = None,
) -> dict:
    """Compute reminder/follow-up urgency for one lead (pure: no DB queries).

    Pass ``cfg`` (from ``_lifecycle_cfg``) to reuse thresholds across many
    leads; otherwise thresholds are read once via ``db`` (or defaults).
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    settings = cfg if cfg is not None else _lifecycle_cfg(db)
    age = _age_hours(lead, current)
    reply_state = (getattr(lead, "reply_state", "unknown") or "unknown")
    if reply_state not in REPLY_STATES:
        reply_state = "unknown"
    follow_up_count = int(getattr(lead, "follow_up_count", 0) or 0)

    needs_reply_check = False
    is_overdue = False
    is_cold = False
    follow_up_ready = False
    if age is not None and reply_state == "unknown":
        needs_reply_check = age >= settings["delay_hours"]
        is_overdue = age >= settings["second_hours"]
    m2_waiting = (
        age is not None
        and reply_state == "replied"
        and not _m2_sent(lead)
    )
    if (
        age is not None
        and reply_state in ("unknown", "no_reply")
        and not _m2_sent(lead)
        and age >= settings["cold_days"] * 24
        and follow_up_count < settings["max_follow_ups"]
    ):
        is_cold = True
        follow_up_ready = bool(settings["follow_up_enabled"])

    if m2_waiting:
        suggested = "mark_replied"
    elif follow_up_ready:
        suggested = "send_followup"
    elif is_overdue or needs_reply_check:
        suggested = "check_reply"
    elif reply_state == "bounced":
        suggested = "archive"
    else:
        suggested = "none"

    return {
        "needs_reply_check": needs_reply_check,
        "is_overdue": is_overdue,
        "is_cold": is_cold,
        "follow_up_ready": follow_up_ready,
        "m2_waiting": m2_waiting,
        "age_hours": round(age, 2) if age is not None else None,
        "suggested_action": suggested,
    }


def get_leads_needing_attention(db: Session) -> dict:
    """Bucket M1-sent leads needing action. Single query, no N+1."""
    cfg = _lifecycle_cfg(db)
    now = datetime.now(timezone.utc)
    # One query: every lead that ever got M1. Bucketing is pure Python.
    candidates = (
        db.query(GroupLead)
        .filter(GroupLead.step1_sent_at.isnot(None))
        .all()
    )
    buckets: dict[str, list[int]] = {
        "reply_check": [],
        "overdue": [],
        "cold_followup_ready": [],
        "m2_waiting": [],
    }
    for lead in candidates:
        urgency = compute_lead_urgency(lead, now=now, cfg=cfg)
        if urgency["m2_waiting"]:
            buckets["m2_waiting"].append(lead.id)
        if urgency["follow_up_ready"]:
            buckets["cold_followup_ready"].append(lead.id)
        if urgency["is_overdue"]:
            buckets["overdue"].append(lead.id)
        elif urgency["needs_reply_check"]:
            buckets["reply_check"].append(lead.id)
    return {
        "reply_check": buckets["reply_check"],
        "overdue": buckets["overdue"],
        "cold_followup_ready": buckets["cold_followup_ready"],
        "m2_waiting": buckets["m2_waiting"],
        "counts": {key: len(ids) for key, ids in buckets.items()},
    }


def mark_reply_checked(lead_id: int, reply_state: str, db: Session) -> GroupLead:
    """Record a manual reply check: stamp + set reply state, atomically."""
    state = (reply_state or "").strip().lower()
    if state not in REPLY_STATES:
        raise ValueError(
            f"Invalid reply_state {reply_state!r}. Allowed: {', '.join(REPLY_STATES)}."
        )
    try:
        lead = db.get(GroupLead, lead_id)
        if lead is None:
            raise ValueError(f"GroupLead {lead_id} not found.")
        if _ensure_aware(getattr(lead, "step1_sent_at", None)) is None:
            raise ValueError("M1 not sent yet.")
        lead.last_checked_at = datetime.now(timezone.utc)
        lead.reply_state = state
        # Status stays step1_sent: M2 unlocks via the Phase 1 gap logic.
        db.commit()
        db.refresh(lead)
        return lead
    except Exception:
        db.rollback()
        logger.exception("mark_reply_checked failed for lead %s.", lead_id)
        raise


def record_follow_up_sent(lead_id: int, db: Session) -> GroupLead:
    """Record a cold-lead follow-up via the Phase 1 quota pipeline."""
    from app.services import dm_safety

    try:
        lead = db.get(GroupLead, lead_id)
        if lead is None:
            raise ValueError(f"GroupLead {lead_id} not found.")
        account = dm_safety.resolve_account(
            db, getattr(lead, "assigned_account_id", None)
        )
        # Reuses the Phase 1 atomic counter+stamp transaction (step=3).
        dm_safety.record_dm_sent(account.id, 3, db, lead_id)
        updated = db.get(GroupLead, lead_id)
        if updated is None:
            raise ValueError(f"GroupLead {lead_id} not found.")
        db.refresh(updated)
        return updated
    except Exception:
        db.rollback()
        logger.exception("record_follow_up_sent failed for lead %s.", lead_id)
        raise
