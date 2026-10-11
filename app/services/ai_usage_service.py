"""AI usage ledger: per-call cost metering + rollups (never raises)."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.system import AiUsage

logger = logging.getLogger("pod-automation")

CALL_TYPES: tuple[str, ...] = ("caption", "hashtag", "variation", "classify", "other")

_FALLBACK_RATES: dict[str, float] = {
    "ai_cost_groq_per_1k_in": 0.0,
    "ai_cost_groq_per_1k_out": 0.0,
    "ai_cost_openai_per_1k_in": 0.005,
    "ai_cost_openai_per_1k_out": 0.015,
}


def _cost_rate(db: Optional[Session], provider: str, direction: str) -> float:
    """Read the per-1k-token rate for a provider/direction.

    Falls back to canonical defaults (Groq free, OpenAI 0.005/0.015)
    when the setting was never persisted to the DB.
    """
    name = (provider or "").strip().lower()
    if name not in ("groq", "openai"):
        return 0.0
    key = f"ai_cost_{name}_per_1k_{direction}"
    fallback = _FALLBACK_RATES.get(key, 0.0)
    if db is None:
        return fallback
    try:
        from app.services import settings_service

        stored = settings_service.get_setting(db, key, None)
        if stored is None:
            return fallback
        return max(0.0, float(str(stored).strip()))
    except (TypeError, ValueError, AttributeError):
        return fallback
    except Exception:
        logger.exception("Failed to read AI cost rate %s.", key)
        return fallback


def record_ai_call(
    db: Session,
    provider: str,
    model: str,
    call_type: str = "other",
    tokens_in: int = 0,
    tokens_out: int = 0,
    success: bool = True,
    error_type: Optional[str] = None,
) -> None:
    """Meter one provider call. NEVER raises — usage logging is best-effort."""
    try:
        kind = (call_type or "other").strip().lower()
        if kind not in CALL_TYPES:
            kind = "other"
        try:
            in_count = max(0, int(tokens_in or 0))
        except (TypeError, ValueError):
            in_count = 0
        try:
            out_count = max(0, int(tokens_out or 0))
        except (TypeError, ValueError):
            out_count = 0
        cost = (
            in_count / 1000.0 * _cost_rate(db, provider, "in")
            + out_count / 1000.0 * _cost_rate(db, provider, "out")
        )
        row = AiUsage(
            provider=(provider or "mock").strip().lower() or "mock",
            model=(model or "").strip()[:80],
            call_type=kind,
            tokens_in=in_count,
            tokens_out=out_count,
            cost_usd=round(cost, 6),
            success=bool(success),
            error_type=(error_type or None),
        )
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("AI usage record failed (flow continues).")


def get_usage_summary(db: Session, days: int = 30) -> dict:
    """Roll up usage by provider + by day. Two queries, no N+1."""
    window = max(1, min(365, int(days)))
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window)
    # The day rollup spans back to the 1st so month-to-date stays exact
    # even for small windows; by_day still returns only the window.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_cutoff = min(cutoff, month_start)

    from sqlalchemy import case

    provider_rows = (
        db.query(
            AiUsage.provider,
            func.count(AiUsage.id).label("calls"),
            func.coalesce(func.sum(AiUsage.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AiUsage.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AiUsage.cost_usd), 0.0).label("cost_usd"),
            func.coalesce(
                func.sum(case((AiUsage.success.is_(True), 1), else_=0)), 0
            ).label("ok"),
        )
        .filter(AiUsage.created_at >= cutoff)
        .group_by(AiUsage.provider)
        .all()
    )
    day_rows = (
        db.query(
            func.date(AiUsage.created_at).label("day"),
            func.count(AiUsage.id).label("calls"),
            func.coalesce(func.sum(AiUsage.cost_usd), 0.0).label("cost_usd"),
        )
        .filter(AiUsage.created_at >= day_cutoff)
        .group_by(func.date(AiUsage.created_at))
        .order_by(func.date(AiUsage.created_at).asc())
        .all()
    )
    by_provider = []
    totals = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
    for row in provider_rows:
        calls = int(row.calls or 0)
        ok = int(row.ok or 0)
        entry = {
            "provider": row.provider,
            "calls": calls,
            "tokens_in": int(row.tokens_in or 0),
            "tokens_out": int(row.tokens_out or 0),
            "cost_usd": round(float(row.cost_usd or 0.0), 4),
            "success_rate": round(ok / calls, 4) if calls else 0.0,
        }
        by_provider.append(entry)
        totals["calls"] += calls
        totals["tokens_in"] += entry["tokens_in"]
        totals["tokens_out"] += entry["tokens_out"]
        totals["cost_usd"] += entry["cost_usd"]
    totals["cost_usd"] = round(totals["cost_usd"], 4)
    by_day = [
        {"date": str(row.day), "calls": int(row.calls or 0),
         "cost_usd": round(float(row.cost_usd or 0.0), 4)}
        for row in day_rows
        if str(row.day) >= cutoff.strftime("%Y-%m-%d")
    ]
    month_prefix = now.strftime("%Y-%m-01")
    month_calls = 0
    month_cost = 0.0
    for row in day_rows:
        if str(row.day) >= month_prefix:
            month_calls += int(row.calls or 0)
            month_cost += float(row.cost_usd or 0.0)
    return {
        "by_provider": sorted(by_provider, key=lambda e: e["cost_usd"], reverse=True),
        "by_day": by_day,
        "totals": totals,
        "month_to_date": {
            "calls": month_calls,
            "cost_usd": round(month_cost, 4),
        },
    }
