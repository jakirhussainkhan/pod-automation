"""Dashboard statistics + overview API router."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.dashboard import DashboardStats
from app.services import post_service

logger = logging.getLogger("pod-automation")

router: APIRouter = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats_endpoint(db: Session = Depends(get_db)) -> DashboardStats:
    """Return aggregated dashboard statistics."""
    return DashboardStats(**post_service.get_dashboard_stats(db))


@router.get("/overview")
def dashboard_overview_endpoint(db: Session = Depends(get_db)) -> dict:
    """Return the Overview Dashboard aggregate in a single call.

    Shape:
        {
          "summary": {
            "total_products": int,
            "active_leads": int,
            "messages_sent_today": int,
            "conversion_revenue": float,
            "pending_actions": {
              "total": int, "reply_check": int, "overdue": int,
              "m2_waiting": int, "cold": int,
            },
          },
          "accounts": [...],
          "recent_activity": [...],
        }

    Each section degrades independently: a failing subsection logs and
    returns a safe default so one bad query never 500s the whole page.
    """
    from app.models.activity_log import ActivityLog
    from app.models.group_lead import GroupLead
    from app.models.product import Product
    from app.services import account_service, group_service, lead_lifecycle, log_service

    # -- Summary: products -------------------------------------------------
    try:
        total_products = int(db.query(func.count(Product.id)).scalar() or 0)
    except Exception:
        logger.exception("Overview: product count failed.")
        total_products = 0

    # -- Summary: active leads (everything not yet converted) --------------
    try:
        active_leads = int(
            db.query(func.count(GroupLead.id))
            .filter(GroupLead.status != "converted")
            .scalar()
            or 0
        )
    except Exception:
        logger.exception("Overview: active-lead count failed.")
        active_leads = 0

    # -- Summary: messages sent today (M1/M2/M3 stamps >= UTC midnight) ----
    try:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        messages_sent_today = int(
            db.query(func.count(GroupLead.id))
            .filter(
                or_(
                    GroupLead.step1_sent_at >= start_of_day,
                    GroupLead.step2_sent_at >= start_of_day,
                    GroupLead.follow_up_sent_at >= start_of_day,
                )
            )
            .scalar()
            or 0
        )
    except Exception:
        logger.exception("Overview: messages-sent-today count failed.")
        messages_sent_today = 0

    # -- Summary: conversion revenue (reuse existing rollup) ---------------
    try:
        conversion_revenue = float(group_service.revenue_stats(db)["total_revenue"])
    except Exception:
        logger.exception("Overview: revenue rollup failed.")
        conversion_revenue = 0.0

    # -- Summary: pending actions (reuse attention buckets) ----------------
    pending_actions = {
        "total": 0,
        "reply_check": 0,
        "overdue": 0,
        "m2_waiting": 0,
        "cold": 0,
    }
    try:
        attention = lead_lifecycle.get_leads_needing_attention(db)
        counts = attention.get("counts", {}) or {}
        pending_actions["reply_check"] = int(counts.get("reply_check") or 0)
        pending_actions["overdue"] = int(counts.get("overdue") or 0)
        pending_actions["m2_waiting"] = int(counts.get("m2_waiting") or 0)
        pending_actions["cold"] = int(counts.get("cold_followup_ready") or 0)
        pending_actions["total"] = (
            pending_actions["reply_check"]
            + pending_actions["overdue"]
            + pending_actions["m2_waiting"]
            + pending_actions["cold"]
        )
    except Exception:
        logger.exception("Overview: attention buckets failed.")

    # -- Accounts: reuse the list service (no new queries per account) -----
    accounts: list[dict] = []
    try:
        for row in account_service.list_accounts(db, include_inactive=True):
            daily_cap = int(row.get("daily_limit") or 20)
            hourly_cap = int(row.get("hourly_limit") or 10)
            today_sent = int(row.get("daily_used") or 0)
            accounts.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "handle": row.get("handle"),
                    "persona_name": row.get("persona_name"),
                    "health_status": row.get("health_status") or "healthy",
                    "health_note": row.get("health_note"),
                    "warnings_count": int(row.get("warnings_count") or 0),
                    "is_active": bool(row.get("is_active", True)),
                    "today_sent": today_sent,
                    "daily_cap": daily_cap,
                    "daily_used": today_sent,
                    "daily_limit": daily_cap,
                    "hourly_used": int(row.get("hourly_used") or 0),
                    "hourly_limit": hourly_cap,
                    "total_dms_sent": int(row.get("total_dms_sent") or 0),
                    "last_active_at": row.get("last_active_at"),
                    "restricted_until": row.get("restricted_until"),
                }
            )
    except Exception:
        logger.exception("Overview: account list failed.")
        accounts = []

    # -- Recent activity: last 10 logs -------------------------------------
    recent_activity: list[dict] = []
    try:
        entries = log_service.list_logs(db, skip=0, limit=10)
        for entry in entries:
            created = getattr(entry, "created_at", None)
            # SQLite returns naive datetimes: treat as UTC for the API.
            if created is not None and getattr(created, "tzinfo", None) is None:
                created = created.replace(tzinfo=timezone.utc)
            recent_activity.append(
                {
                    "id": entry.id,
                    "event": entry.event_type,
                    "event_type": entry.event_type,
                    "description": entry.message,
                    "message": entry.message,
                    "level": entry.level,
                    "created_at": created.isoformat() if created else None,
                }
            )
    except Exception:
        logger.exception("Overview: recent activity failed.")
        recent_activity = []

    _ = ActivityLog  # Keep import visible for future enrichment.
    return {
        "summary": {
            "total_products": total_products,
            "active_leads": active_leads,
            "messages_sent_today": messages_sent_today,
            "conversion_revenue": round(conversion_revenue, 2),
            "pending_actions": pending_actions,
        },
        "accounts": accounts,
        "recent_activity": recent_activity,
    }
