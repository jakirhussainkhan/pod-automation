"""Group health stats API router (Phase 3: daily snapshots + digest)."""

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from app.database.session import get_db
from app.services import group_stats as stats_service

logger = logging.getLogger("pod-automation")

router: APIRouter = APIRouter(prefix="/api/stats", tags=["stats"])


class DailyStatUpsert(BaseModel):
    """Daily snapshot payload; omitted funnel fields auto-fill when enabled."""

    stat_date: date
    member_count: Optional[int] = Field(default=None, ge=0)
    new_members: Optional[int] = Field(default=None, ge=0)
    posts_published: Optional[int] = Field(default=None, ge=0)
    comments_received: Optional[int] = Field(default=None, ge=0)
    leads_captured: Optional[int] = Field(default=None, ge=0)
    m1_sent: Optional[int] = Field(default=None, ge=0)
    m2_sent: Optional[int] = Field(default=None, ge=0)
    converted: Optional[int] = Field(default=None, ge=0)
    revenue: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = Field(default=None, max_length=2000)


def _parse_day(value: Optional[str], name: str) -> Optional[date]:
    """Parse a YYYY-MM-DD query param, 422 on bad format."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"{name} must be a YYYY-MM-DD date.",
        )


@router.get("/daily", summary="Daily group stats range for charts", description="Ascending daily snapshot rows for [start, end], zero-filling days without rows. Defaults to the last chart_days. Range capped at 365 days.")
def daily_range(
    start: Optional[str] = Query(None, description="YYYY-MM-DD start"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD end"),
    db: Session = Depends(get_db),
) -> dict:
    """Return the chart-ready daily range."""
    window = stats_service.get_chart_days(db)
    today = datetime.now(timezone.utc).date()
    end_day = _parse_day(end, "end") or today
    start_day = _parse_day(start, "start") or (end_day - timedelta(days=window - 1))
    if (end_day - start_day).days > 365:
        raise HTTPException(status_code=422, detail="Range capped at 365 days.")
    try:
        days = stats_service.get_stats_range(db, start_day, end_day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"items": days, "start": start_day.isoformat(), "end": end_day.isoformat()}


@router.post("/daily", summary="Create or update a daily stat snapshot", description="Upsert one YYYY-MM-DD snapshot row. Omitted funnel fields auto-fill from live data when stats_auto_compute is on. Future dates and negative numbers are rejected.")
def upsert_daily(data: DailyStatUpsert, db: Session = Depends(get_db)) -> dict:
    """Insert or update a daily snapshot."""
    payload = {k: v for k, v in data.model_dump().items() if k != "stat_date"}
    try:
        row = stats_service.upsert_daily_stat(db, data.stat_date, payload)
    except ValueError as exc:
        message = str(exc)
        if "future" in message:
            raise HTTPException(status_code=422, detail=message)
        raise HTTPException(status_code=422, detail=message)
    return stats_service.row_to_dict(row)


@router.get("/today", summary="Today's stat snapshot (auto-filled)", description="Today's row, auto-computed from live data when missing. Powers the dashboard + Groups snapshot widgets.")
def today_snapshot(db: Session = Depends(get_db)) -> dict:
    """Return today's snapshot, computing live values for missing fields."""
    today = datetime.now(timezone.utc).date()
    try:
        row = stats_service.upsert_daily_stat(db, today, {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return stats_service.row_to_dict(row)


@router.get("/weekly-digest", summary="This week vs last week deltas", description="Aggregated this-week / last-week totals with percent-change deltas and up/down/flat trends. Week boundary follows the digest_week_start setting.")
def weekly_digest(db: Session = Depends(get_db)) -> dict:
    """Return the weekly comparison digest."""
    return stats_service.get_weekly_digest(db, stats_service.get_week_start(db))


@router.get("/templates", summary="Per-template performance", description="Funnel rollup per psychology template (queued/copied/posted/leads/converted/revenue), sorted by revenue DESC. Single GROUP BY query.")
def template_performance(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """Return per-template performance for the trailing window."""
    return {"items": stats_service.get_template_performance(db, days), "days": days}
