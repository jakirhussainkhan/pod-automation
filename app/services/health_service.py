"""System health snapshot: DB, Facebook, AI, queue, backup, disk."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.models.group_lead import GroupLead
from app.models.group_post_queue import GroupPostQueue
from app.models.post import Post
from app.services import backup_service

logger = logging.getLogger("pod-automation")


def _db_path() -> Path:
    """Resolve the live SQLite file from DATABASE_URL."""
    url = get_settings().DATABASE_URL
    path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else url
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate


def _check_db(db: Session) -> dict:
    """Check DB reachability, size, and table inventory."""
    from sqlalchemy import text

    try:
        from app.database.base import Base

        db.execute(text("SELECT 1"))
        path = _db_path()
        size_mb = round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else 0.0
        tables = len(Base.metadata.tables)
        return {"ok": True, "size_mb": size_mb, "table_count": tables}
    except Exception as exc:
        logger.exception("Health DB check failed.")
        return {"ok": False, "error": str(exc)[:200]}


def _check_queue(db: Session) -> dict:
    """Count pending scheduled posts + untouched leads."""
    try:
        pending_posts = (
            db.query(func.count(Post.id))
            .filter(Post.status == "scheduled")
            .scalar()
            or 0
        )
        pending_leads = (
            db.query(func.count(GroupLead.id))
            .filter(GroupLead.status == "unsent")
            .scalar()
            or 0
        )
        queued_posts = (
            db.query(func.count(GroupPostQueue.id))
            .filter(GroupPostQueue.status == "queued")
            .scalar()
            or 0
        )
        return {
            "ok": True,
            "pending_posts": int(pending_posts),
            "pending_leads": int(pending_leads),
            "queued_posts": int(queued_posts),
        }
    except Exception as exc:
        logger.exception("Health queue check failed.")
        return {"ok": False, "error": str(exc)[:200]}


def _check_backup(db: Session) -> dict:
    """Report the freshest successful backup and its age."""
    try:
        latest = backup_service.last_backup_at(db)
        if latest is None:
            return {"ok": False, "last_backup_at": None, "age_hours": None,
                    "error": "No successful backup yet."}
        age_hours = round((datetime.now(timezone.utc) - latest).total_seconds() / 3600.0, 1)
        return {
            "ok": age_hours < 49.0,
            "last_backup_at": latest.isoformat(),
            "age_hours": age_hours,
        }
    except Exception as exc:
        logger.exception("Health backup check failed.")
        return {"ok": False, "error": str(exc)[:200]}


def _check_disk(db: Session) -> dict:
    """Report backup-dir footprint + activity-log row count."""
    try:
        from app.models.activity_log import ActivityLog

        backup_dir = BASE_DIR / "data" / "backups"
        total = 0
        if backup_dir.exists():
            for child in backup_dir.iterdir():
                if child.is_file():
                    total += child.stat().st_size
        log_rows = db.query(func.count(ActivityLog.id)).scalar() or 0
        return {
            "ok": True,
            "backups_mb": round(total / (1024 * 1024), 2),
            "logs_rows": int(log_rows),
        }
    except Exception as exc:
        logger.exception("Health disk check failed.")
        return {"ok": False, "error": str(exc)[:200]}


def _token_days_left(db: Session) -> tuple[bool, Optional[str], Optional[str], Optional[int]]:
    """Read token dates from settings; return (set, added, expires, days_left)."""
    from app.services import settings_service

    try:
        added = str(settings_service.get_setting(db, "token_added_at", "") or "").strip()
        expires = str(settings_service.get_setting(db, "token_expires_at", "") or "").strip()
        if not expires:
            return False, (added or None), None, None
        stamp = expires[:-1] + "+00:00" if expires.endswith("Z") else expires
        expiry = datetime.fromisoformat(stamp)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        # Ceil so "expires in 4.9 days" reads as 5 days left.
        import math

        total = (expiry - datetime.now(timezone.utc)).total_seconds()
        left = math.ceil(total / 86400.0) if total > 0 else int(total // 86400)
        return True, (added or None), expires, left
    except Exception:
        logger.exception("Token date parse failed.")
        return False, None, None, None


def token_status(db: Session) -> dict:
    """Facebook token expiry state for banners and API consumers."""
    from app.config import get_settings as _settings

    configured = _settings().has_facebook_credentials()
    present, added, expires, left = _token_days_left(db)
    token_set = bool(configured or present)
    if not token_set or left is None:
        level = "expired"
    elif left <= 0:
        level = "expired"
    elif left <= 7:
        level = "urgent"
    elif left <= 30:
        level = "soon"
    else:
        level = "ok"
    return {
        "token_set": token_set,
        "added_at": added,
        "expires_at": expires,
        "days_left": left,
        "warning_level": level,
    }


async def get_system_health(db: Session) -> dict:
    """Assemble the full health snapshot; each check is failure-isolated."""
    try:
        from app.services import settings_service

        kill = settings_service.is_kill_switch_active(db)
    except Exception:
        kill = False

    try:
        from app.services.facebook.status import get_facebook_status

        fb_live = await asyncio.wait_for(get_facebook_status(), timeout=8.0)
        fb = {
            "ok": bool(fb_live.get("token_valid")),
            "page_name": fb_live.get("page_name"),
            "token_set": bool(fb_live.get("configured")),
            "token_days_left": None,
        }
    except Exception as exc:
        logger.warning("Health FB check failed: %s", exc)
        fb = {"ok": False, "page_name": None, "token_set": False,
              "token_days_left": None, "error": "check failed"}
    try:
        token = token_status(db)
        fb["token_days_left"] = token["days_left"]
        if fb.get("token_set") is False and token["token_set"]:
            fb["token_set"] = True
    except Exception:
        pass

    try:
        from app.models.system import AiUsage

        last_ok = (
            db.query(AiUsage)
            .filter(AiUsage.success.is_(True))
            .order_by(AiUsage.id.desc())
            .first()
        )
        ai = {
            "ok": True,
            "primary_provider": get_settings().AI_PROVIDER,
            "last_success_at": last_ok.created_at.isoformat() if last_ok and last_ok.created_at else None,
        }
    except Exception as exc:
        logger.exception("Health AI check failed.")
        ai = {"ok": False, "error": str(exc)[:200]}

    return {
        "db": _check_db(db),
        "fb": fb,
        "ai": ai,
        "queue": _check_queue(db),
        "kill_switch": bool(kill),
        "backup": _check_backup(db),
        "disk": _check_disk(db),
        "accounts": _check_accounts(db),
    }


def _check_accounts(db: Session) -> dict:
    """Summarize ghost-account fleet health (failure-isolated)."""
    try:
        from app.models.fb_account import FbAccount

        rows = db.query(FbAccount).all()
        now = datetime.now(timezone.utc)
        total = len(rows)
        active = warned = banned = restricted_now = 0
        next_available: Optional[str] = None
        soonest: Optional[datetime] = None
        for account in rows:
            if bool(getattr(account, "is_active", False)):
                active += 1
            health = (getattr(account, "health_status", "healthy") or "healthy").lower()
            if health == "warned":
                warned += 1
            if health == "banned":
                banned += 1
            restricted = getattr(account, "restricted_until", None)
            if restricted is not None:
                if getattr(restricted, "tzinfo", None) is None:
                    restricted = restricted.replace(tzinfo=timezone.utc)
                if restricted > now:
                    restricted_now += 1
                    if soonest is None or restricted < soonest:
                        soonest = restricted
        if soonest is not None:
            next_available = soonest.isoformat()
        return {
            "ok": total > 0 and active > 0 and banned < total,
            "total": total,
            "active": active,
            "warned": warned,
            "banned": banned,
            "restricted_now": restricted_now,
            "next_available_at": next_available,
        }
    except Exception as exc:
        logger.exception("Health accounts check failed.")
        return {"ok": False, "error": str(exc)[:200]}
