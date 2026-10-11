"""DM Safety layer: M1->M2 minimum gap + per-account hourly/daily rate limits."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.fb_account import FbAccount
from app.models.group_lead import GroupLead

logger = logging.getLogger("pod-automation")

DEFAULT_MIN_GAP_SECONDS = 300
DEFAULT_HOURLY_CAP = 10
DEFAULT_DAILY_CAP = 20


def _ensure_aware(value: Optional[datetime]) -> Optional[datetime]:
    """Coerce a stored datetime to timezone-aware UTC (SQLite returns naive)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_int_setting(db: Optional[Session], key: str, fallback: int) -> int:
    """Read an int setting from app_settings, falling back on any failure."""
    if db is None:
        return fallback
    try:
        from app.services import settings_service

        raw = settings_service.get_setting(db, key, None)
        if raw is None:
            return fallback
        return int(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return fallback
    except Exception:
        logger.exception("Failed to read setting %s; using fallback.", key)
        return fallback


def get_min_gap_seconds(db: Optional[Session] = None) -> int:
    """Return the configured M1->M2 gap (floor 60s, default 300s)."""
    return max(60, _get_int_setting(db, "dm_min_gap_seconds", DEFAULT_MIN_GAP_SECONDS))


def get_hourly_cap(db: Optional[Session] = None) -> int:
    """Return the configured global hourly DM cap (default 10)."""
    raw = _get_int_setting(db, "dm_hourly_cap", DEFAULT_HOURLY_CAP)
    return max(1, min(50, raw))


def get_daily_cap(db: Optional[Session] = None) -> int:
    """Return the configured global daily DM cap (default 20)."""
    raw = _get_int_setting(db, "dm_daily_cap", DEFAULT_DAILY_CAP)
    return max(1, min(200, raw))


def get_cold_lead_days(db: Optional[Session] = None) -> int:
    """Return the configured cold-lead threshold in days (default 3)."""
    raw = _get_int_setting(db, "cold_lead_days", 3)
    return max(1, min(30, raw))


def is_multi_account_enabled(db: Optional[Session] = None) -> bool:
    """Feature flag for rotation (default OFF = single-account behavior)."""
    if db is None:
        return False
    try:
        from app.services import settings_service

        raw = settings_service.get_setting(db, "multi_account_enabled", "false")
        return str(raw).strip().lower() == "true"
    except Exception:
        logger.exception("Failed to read multi_account_enabled; assuming off.")
        return False


def get_rotation_mode(db: Optional[Session] = None) -> str:
    """Return priority | round_robin | niche_match (default priority)."""
    if db is None:
        return "priority"
    try:
        from app.services import settings_service

        raw = str(settings_service.get_setting(db, "account_rotation_mode", "priority"))
        mode = raw.strip().lower()
        return mode if mode in ("priority", "round_robin", "niche_match") else "priority"
    except Exception:
        logger.exception("Failed to read rotation mode; assuming priority.")
        return "priority"


def get_collision_window_days(db: Optional[Session] = None) -> int:
    """Same-group collision window in days (default 7)."""
    return max(1, min(90, _get_int_setting(db, "account_collision_window_days", 7)))


def get_warning_pause_hours(db: Optional[Session] = None) -> int:
    """Auto-pause after a warning, in hours; 0 disables auto-pause."""
    return max(0, min(720, _get_int_setting(db, "account_warning_pause_hours", 48)))


def get_ban_recovery_days(db: Optional[Session] = None) -> int:
    """Suggested post-ban wait in days (default 30)."""
    return max(1, min(365, _get_int_setting(db, "account_ban_recovery_days", 30)))


def get_default_account(db: Session) -> FbAccount:
    """Return the first active account (or any account), creating a seed row."""
    account = (
        db.query(FbAccount)
        .filter(FbAccount.is_active.is_(True))
        .order_by(FbAccount.id.asc())
        .first()
    )
    if account is None:
        account = db.query(FbAccount).order_by(FbAccount.id.asc()).first()
    if account is None:
        now = datetime.now(timezone.utc)
        account = FbAccount(
            name="Default Account",
            daily_dm_count=0,
            hourly_dm_count=0,
            last_hourly_reset_at=now,
            last_daily_reset_at=now,
            daily_limit=DEFAULT_DAILY_CAP,
            hourly_limit=DEFAULT_HOURLY_CAP,
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def resolve_account(db: Session, account_id: Optional[int] = None) -> FbAccount:
    """Resolve an explicit account id, falling back to the default account."""
    if account_id is not None:
        account = db.get(FbAccount, account_id)
        if account is not None:
            return account
    return get_default_account(db)


def _maybe_reset_counters(account: FbAccount, now: datetime) -> bool:
    """Reset stale hourly/daily counters in place; return True when changed."""
    changed = False
    hourly_at = _ensure_aware(account.last_hourly_reset_at) or now
    daily_at = _ensure_aware(account.last_daily_reset_at) or now
    if (now - hourly_at) >= timedelta(hours=1):
        account.hourly_dm_count = 0
        account.last_hourly_reset_at = now
        changed = True
    if (now - daily_at) >= timedelta(hours=24):
        account.daily_dm_count = 0
        account.last_daily_reset_at = now
        changed = True
    return changed


def can_send_step2(
    lead: GroupLead,
    now: Optional[datetime] = None,
    gap_seconds: Optional[int] = None,
    db: Optional[Session] = None,
) -> tuple[bool, str]:
    """Check whether Message 2 may be sent for a lead.

    Returns ``(allowed, reason)``. ``gap_seconds`` overrides the
    configured ``dm_min_gap_seconds`` (used by the API layer which passes
    the live setting value); otherwise falls back to ``db``/default 300s.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    gap = gap_seconds if gap_seconds is not None else get_min_gap_seconds(db)
    gap = max(60, int(gap))
    sent_at = _ensure_aware(getattr(lead, "step1_sent_at", None))
    if sent_at is None:
        return (False, "M1 not sent yet")
    elapsed = (current - sent_at).total_seconds()
    if elapsed < gap:
        seconds_left = int(gap - elapsed)
        # Round up so the UI never shows 0s while still locked.
        if (gap - elapsed) > seconds_left:
            seconds_left += 1
        seconds_left = max(1, seconds_left)
        return (False, f"Wait {seconds_left}s before sending M2")
    return (True, "OK")


def seconds_until_m2(
    lead: GroupLead,
    now: Optional[datetime] = None,
    gap_seconds: Optional[int] = None,
    db: Optional[Session] = None,
) -> int:
    """Return whole seconds remaining before M2 is allowed (0 when ready)."""
    allowed, reason = can_send_step2(lead, now=now, gap_seconds=gap_seconds, db=db)
    if allowed:
        return 0
    import re

    match = re.search(r"Wait (\d+)s", reason)
    if match:
        try:
            return max(0, int(match.group(1)))
        except (TypeError, ValueError):
            return 0
    # Non-countdown block (e.g. M1 not sent): report full gap.
    gap = gap_seconds if gap_seconds is not None else get_min_gap_seconds(db)
    return max(0, int(gap))


def check_rate_limit(account_id: Optional[int], db: Session) -> tuple[bool, str]:
    """Check hourly/daily quota for an account (lazy counter resets).

    ``account_id=None`` resolves to the default account (same shape).
    Resets the hourly counter when ``last_hourly_reset_at`` is >1h old and
    the daily counter when ``last_daily_reset_at`` is >24h old, committing
    the reset so concurrent readers observe fresh counters.
    """
    from sqlalchemy.exc import SQLAlchemyError

    now = datetime.now(timezone.utc)
    try:
        account = db.get(FbAccount, account_id)
        if account is None:
            account = resolve_account(db, None)
        if _maybe_reset_counters(account, now):
            db.commit()
            db.refresh(account)
        hourly_limit = int(account.hourly_limit or get_hourly_cap(db))
        daily_limit = int(account.daily_limit or get_daily_cap(db))
        # Global caps from settings act as an additional ceiling.
        hourly_limit = min(hourly_limit, get_hourly_cap(db))
        daily_limit = min(daily_limit, get_daily_cap(db))
        if int(account.hourly_dm_count or 0) >= hourly_limit:
            hourly_at = _ensure_aware(account.last_hourly_reset_at) or now
            reset_at = hourly_at + timedelta(hours=1)
            wait_min = max(1, int((reset_at - now).total_seconds() // 60))
            return (False, f"Hourly cap reached — wait {wait_min} min")
        if int(account.daily_dm_count or 0) >= daily_limit:
            return (False, "Daily cap reached — resume tomorrow")
        return (True, "OK")
    except SQLAlchemyError:
        db.rollback()
        raise


def can_send_followup(
    lead: GroupLead,
    now: Optional[datetime] = None,
    db: Optional[Session] = None,
) -> tuple[bool, str]:
    """Check whether a cold-lead follow-up (M3) may be sent.

    Same ``(allowed, reason)`` shape as :func:`can_send_step2`.
    """
    from app.services import lead_lifecycle as lifecycle

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    sent_at = _ensure_aware(getattr(lead, "step1_sent_at", None))
    if sent_at is None:
        return (False, "M1 not sent yet")
    if (getattr(lead, "reply_state", "unknown") or "unknown") == "replied":
        return (False, "Lead replied — send M2 instead")
    if not lifecycle.is_follow_up_enabled(db):
        return (False, "Follow-ups disabled")
    max_ups = lifecycle.get_max_follow_ups(db)
    if int(getattr(lead, "follow_up_count", 0) or 0) >= max_ups:
        return (False, "Follow-up limit reached")
    cold_days = get_cold_lead_days(db)
    age_hours = (current - sent_at).total_seconds() / 3600.0
    if age_hours < cold_days * 24:
        return (False, f"Lead not cold yet ({age_hours:.1f}h old)")
    return (True, "OK")


def record_dm_sent(account_id: int, step: int, db: Session, lead_id: int) -> None:
    """Record a sent DM: bump quota counters + stamp the lead, atomically.

    ``step == 1`` sets ``lead.step1_sent_at`` and status ``step1_sent``
    (plus schedules ``follow_up_due_at`` = now + ``cold_lead_days``);
    ``step == 2`` sets ``lead.step2_sent_at`` and status ``step2_sent``;
    ``step == 3`` records a cold-lead follow-up (M3): sets
    ``follow_up_sent_at``, increments ``follow_up_count`` and sets status
    ``follow_up_sent``.
    The counter increment and lead stamp share one transaction so rapid
    double-clicks cannot consume quota without stamping (or vice versa).
    """
    if step not in (1, 2, 3):
        raise ValueError("step must be 1, 2, or 3.")
    now = datetime.now(timezone.utc)
    try:
        account = db.get(FbAccount, account_id)
        if account is None:
            account = resolve_account(db, None)
        if _maybe_reset_counters(account, now):
            pass  # counters reset in the same atomic commit below.
        lead = db.get(GroupLead, lead_id)
        if lead is None:
            raise ValueError(f"GroupLead {lead_id} not found.")
        account.hourly_dm_count = int(account.hourly_dm_count or 0) + 1
        account.daily_dm_count = int(account.daily_dm_count or 0) + 1
        account.total_dms_sent = int(getattr(account, "total_dms_sent", 0) or 0) + 1
        account.last_active_at = now
        account.last_hourly_reset_at = _ensure_aware(account.last_hourly_reset_at) or now
        account.last_daily_reset_at = _ensure_aware(account.last_daily_reset_at) or now
        if getattr(lead, "assigned_account_id", None) is None:
            lead.assigned_account_id = account.id
        if step == 1:
            lead.step1_sent_at = now
            lead.status = "step1_sent"
            try:
                lead.follow_up_due_at = now + timedelta(days=get_cold_lead_days(db))
            except Exception:
                logger.exception("Failed to schedule follow_up_due_at; leaving unset.")
        elif step == 2:
            lead.step2_sent_at = now
            lead.status = "step2_sent"
        else:
            lead.follow_up_sent_at = now
            lead.follow_up_count = int(getattr(lead, "follow_up_count", 0) or 0) + 1
            lead.status = "follow_up_sent"
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("record_dm_sent failed for lead %s step %s.", lead_id, step)
        raise


def quota_snapshot(db: Session, account_id: Optional[int] = None) -> dict:
    """Return quota counters/limits + next hourly reset for the status API."""
    now = datetime.now(timezone.utc)
    account = resolve_account(db, account_id)
    if _maybe_reset_counters(account, now):
        try:
            db.commit()
            db.refresh(account)
        except Exception:
            db.rollback()
            logger.exception("Quota reset commit failed.")
    hourly_limit = min(int(account.hourly_limit or 10), get_hourly_cap(db))
    daily_limit = min(int(account.daily_limit or 20), get_daily_cap(db))
    hourly_at = _ensure_aware(account.last_hourly_reset_at) or now
    next_reset = hourly_at + timedelta(hours=1)
    if next_reset <= now:
        next_reset = now + timedelta(hours=1)
    payload = {
        "account_id": account.id,
        "account_name": account.name,
        "hourly_used": int(account.hourly_dm_count or 0),
        "hourly_limit": hourly_limit,
        "daily_used": int(account.daily_dm_count or 0),
        "daily_limit": daily_limit,
        "next_hourly_reset_at": next_reset.isoformat(),
    }
    # Per-account breakdown (backward compatible: top-level fields stay).
    try:
        accounts = (
            db.query(FbAccount)
            .filter(FbAccount.is_active.is_(True))
            .order_by(FbAccount.priority.asc(), FbAccount.id.asc())
            .all()
        )
        touched = False
        for candidate in accounts:
            if _maybe_reset_counters(candidate, now):
                touched = True
        if touched:
            db.commit()
        breakdown = []
        for candidate in accounts:
            restricted = _ensure_aware(getattr(candidate, "restricted_until", None))
            breakdown.append({
                "account_id": candidate.id,
                "name": candidate.name,
                "handle": getattr(candidate, "handle", None),
                "hourly_used": int(candidate.hourly_dm_count or 0),
                "hourly_limit": min(int(candidate.hourly_limit or 10), get_hourly_cap(db)),
                "daily_used": int(candidate.daily_dm_count or 0),
                "daily_limit": min(int(candidate.daily_limit or 20), get_daily_cap(db)),
                "health_status": getattr(candidate, "health_status", "healthy") or "healthy",
                "restricted_until": restricted.isoformat() if restricted else None,
            })
        payload["accounts"] = breakdown
    except Exception:
        logger.exception("Per-account quota breakdown failed.")
        db.rollback()
    return payload


def _account_has_capacity(account: FbAccount, now: datetime, db: Session) -> bool:
    """True when the account is under both hourly and daily ceilings."""
    hourly_at = _ensure_aware(account.last_hourly_reset_at) or now
    daily_at = _ensure_aware(account.last_daily_reset_at) or now
    hourly_used = 0 if (now - hourly_at) >= timedelta(hours=1) else int(account.hourly_dm_count or 0)
    daily_used = 0 if (now - daily_at) >= timedelta(hours=24) else int(account.daily_dm_count or 0)
    hourly_limit = min(int(account.hourly_limit or 10), get_hourly_cap(db))
    daily_limit = min(int(account.daily_limit or 20), get_daily_cap(db))
    return hourly_used < hourly_limit and daily_used < daily_limit


def _infer_niche(group_name: Optional[str]) -> Optional[str]:
    """Guess a niche key from a group tag for niche_match routing."""
    tag = (group_name or "").strip().lower()
    if not tag:
        return None
    if any(key in tag for key in ("harley", "biker", "moto", "chopper", "cruiser", "rider")):
        return "harley"
    if "mustang" in tag or "ford" in tag:
        return "mustang"
    if any(key in tag for key in ("jdm", "honda", "toyota", "nissan", "supra", "subaru", "mazda")):
        return "jdm"
    if any(key in tag for key in ("muscle", "hemi", "mopar", "chevy", "corvette", "camaro", "dodge")):
        return "muscle"
    return None


def is_account_blocked_from_group(
    account_id: int, group_name: Optional[str], db: Session, window_days: Optional[int] = None
) -> bool:
    """True when the account hit this group inside the collision window."""
    from app.models.fb_account import AccountGroupBlocked

    tag = (group_name or "").strip()
    if not tag or account_id is None:
        return False
    window = window_days if window_days is not None else get_collision_window_days(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(window)))
    try:
        hit = (
            db.query(AccountGroupBlocked.id)
            .filter(
                AccountGroupBlocked.account_id == account_id,
                func.lower(AccountGroupBlocked.group_name) == tag.lower(),
                AccountGroupBlocked.blocked_at >= cutoff,
            )
            .first()
        )
        return hit is not None
    except Exception:
        logger.exception("Collision check failed; treating as blocked (safe).")
        return True


def block_account_from_group(account_id: int, group_name: str, reason: str, db: Session) -> None:
    """Record a group block (insert-or-ignore on the unique pair)."""
    from sqlalchemy.exc import IntegrityError

    from app.models.fb_account import AccountGroupBlocked

    tag = (group_name or "").strip()[:200]
    if not tag or account_id is None:
        return
    mode = (reason or "manual").strip().lower()
    if mode not in ("collision", "manual", "fb_warning"):
        mode = "manual"
    try:
        db.add(AccountGroupBlocked(
            account_id=account_id, group_name=tag,
            blocked_at=datetime.now(timezone.utc), reason=mode,
        ))
        db.commit()
    except IntegrityError:
        db.rollback()  # Pair already blocked — idempotent no-op.
    except Exception:
        db.rollback()
        logger.exception("Block-group insert failed.")
        raise


def is_account_usable_for_lead(
    account: FbAccount, lead: GroupLead, db: Session, now: Optional[datetime] = None
) -> tuple[bool, str]:
    """Eligibility probe for one account/lead pair (no state change).

    Checks active flag, healthy/warned status, restriction window,
    quota headroom and — when multi-account mode is on — the group
    collision window. Returns ``(usable, reason)``.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if not bool(getattr(account, "is_active", False)):
        return (False, "Account is paused")
    health = (getattr(account, "health_status", "healthy") or "healthy").lower()
    if health not in ("healthy", "warned"):
        return (False, f"Account is {health}")
    restricted = _ensure_aware(getattr(account, "restricted_until", None))
    if restricted is not None and restricted > current:
        return (False, "Account is restricted until " + restricted.isoformat())
    if not _account_has_capacity(account, current, db):
        return (False, "Account is at its DM cap")
    if is_multi_account_enabled(db):
        group_tag = getattr(lead, "group_name", None)
        if group_tag and is_account_blocked_from_group(account.id, group_tag, db):
            return (False, "Account recently posted in this group")
    return (True, "OK")


def get_next_available_account(db: Session, lead: GroupLead) -> Optional[FbAccount]:
    """Pick the best account for a lead under the rotation mode.

    With ``multi_account_enabled=False`` this always returns the default
    single account (100% backward compatible). Otherwise filters to
    active,     healthy/warned, unrestricted accounts with quota headroom
    and no in-window collision for the lead's group.
    """
    if not is_multi_account_enabled(db):
        try:
            return get_default_account(db)
        except Exception:
            logger.exception("Default account lookup failed.")
            return None
    now = datetime.now(timezone.utc)
    mode = get_rotation_mode(db)
    try:
        candidates = (
            db.query(FbAccount)
            .filter(FbAccount.is_active.is_(True))
            .all()
        )
    except Exception:
        logger.exception("Account rotation query failed.")
        return None
    eligible = []
    group_tag = getattr(lead, "group_name", None)
    for account in candidates:
        health = (getattr(account, "health_status", "healthy") or "healthy").lower()
        if health not in ("healthy", "warned"):
            continue
        restricted = _ensure_aware(getattr(account, "restricted_until", None))
        if restricted is not None and restricted > now:
            continue
        if not _account_has_capacity(account, now, db):
            continue
        if group_tag and is_account_blocked_from_group(account.id, group_tag, db):
            continue
        eligible.append(account)
    if not eligible:
        return None

    def _last_active(account: FbAccount) -> datetime:
        return _ensure_aware(getattr(account, "last_active_at", None)) or datetime.min.replace(tzinfo=timezone.utc)

    def _priority(account: FbAccount) -> int:
        try:
            return int(getattr(account, "priority", 100) or 0)
        except (TypeError, ValueError):
            return 100

    if mode == "round_robin":
        eligible.sort(key=lambda a: (_last_active(a), a.id))
    elif mode == "niche_match":
        want = _infer_niche(group_tag)
        eligible.sort(key=lambda a: (
            0 if (getattr(a, "niche_focus", None) or "").lower() == (want or "") and want else 1,
            _priority(a),
            _last_active(a),
        ))
    else:  # priority
        eligible.sort(key=lambda a: (_priority(a), _last_active(a), a.id))
    return eligible[0]


def record_account_warning(account_id: int, note: str, db: Session) -> FbAccount:
    """Log an FB warning: count++, health=warned, optional auto-pause."""
    from app.services import log_service

    account = db.get(FbAccount, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found.")
    try:
        account.warnings_count = int(account.warnings_count or 0) + 1
        account.health_status = "warned"
        account.health_note = (note or "").strip()[:500] or None
        pause = get_warning_pause_hours(db)
        if pause > 0:
            account.restricted_until = datetime.now(timezone.utc) + timedelta(hours=pause)
        db.commit()
        db.refresh(account)
    except Exception:
        db.rollback()
        logger.exception("record_account_warning failed for %s.", account_id)
        raise
    try:
        log_service.add_log(
            db, "account_warned", f"Account {account_id} warned: {account.health_note or 'no detail'}.",
            level="WARNING", entity_type="fb_account", entity_id=account_id,
        )
    except Exception:
        logger.exception("account_warned log failed (non-fatal).")
    return account


def record_account_ban(account_id: int, note: str, db: Session) -> FbAccount:
    """Log an FB ban: health=banned + recovery-window restriction."""
    from app.services import log_service

    account = db.get(FbAccount, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found.")
    try:
        account.health_status = "banned"
        account.health_note = (note or "").strip()[:500] or None
        account.restricted_until = datetime.now(timezone.utc) + timedelta(
            days=get_ban_recovery_days(db))
        db.commit()
        db.refresh(account)
    except Exception:
        db.rollback()
        logger.exception("record_account_ban failed for %s.", account_id)
        raise
    try:
        log_service.add_log(
            db, "account_banned", f"Account {account_id} banned: {account.health_note or 'no detail'}.",
            level="ERROR", entity_type="fb_account", entity_id=account_id,
        )
    except Exception:
        logger.exception("account_banned log failed (non-fatal).")
    return account


def record_account_restore(account_id: int, db: Session) -> FbAccount:
    """Mark an account healthy again (warnings_count is kept as history)."""
    from app.services import log_service

    account = db.get(FbAccount, account_id)
    if account is None:
        raise ValueError(f"Account {account_id} not found.")
    try:
        account.health_status = "healthy"
        account.restricted_until = None
        account.health_note = None
        db.commit()
        db.refresh(account)
    except Exception:
        db.rollback()
        logger.exception("record_account_restore failed for %s.", account_id)
        raise
    try:
        log_service.add_log(
            db, "account_restored", f"Account {account_id} restored to healthy.",
            entity_type="fb_account", entity_id=account_id,
        )
    except Exception:
        logger.exception("account_restored log failed (non-fatal).")
    return account
