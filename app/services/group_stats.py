"""Group health stats: daily snapshots, weekly digest, template performance."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.group_lead import GroupLead
from app.models.group_post_queue import GroupPostQueue
from app.models.group_stats import STAT_NUMERIC_FIELDS, GroupStats

logger = logging.getLogger("pod-automation")

DIGEST_KEYS: tuple[str, ...] = (
    "member_count",
    "new_members",
    "posts_published",
    "comments_received",
    "leads_captured",
    "m1_sent",
    "m2_sent",
    "converted",
    "revenue",
)
"""Metric keys aggregated in the weekly digest."""


def _today_utc() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()


def is_auto_compute(db: Optional[Session] = None) -> bool:
    """Return True unless live auto-fill was disabled in settings."""
    if db is None:
        return True
    try:
        from app.services import settings_service

        raw = settings_service.get_setting(db, "stats_auto_compute", "true")
        return str(raw).strip().lower() != "false"
    except Exception:
        logger.exception("Failed to read stats_auto_compute; assuming enabled.")
        return True


def get_week_start(db: Optional[Session] = None) -> str:
    """Return 'monday' or 'sunday' per settings (default monday)."""
    if db is None:
        return "monday"
    try:
        from app.services import settings_service

        raw = str(settings_service.get_setting(db, "digest_week_start", "monday"))
        return "sunday" if raw.strip().lower() == "sunday" else "monday"
    except Exception:
        logger.exception("Failed to read digest_week_start; assuming monday.")
        return "monday"


def get_chart_days(db: Optional[Session] = None) -> int:
    """Return the chart window in days (default 30, clamped 7..90)."""
    if db is None:
        return 30
    try:
        from app.services import settings_service

        raw = settings_service.get_setting(db, "chart_days", "30")
        return max(7, min(90, int(str(raw).strip())))
    except (TypeError, ValueError, AttributeError):
        return 30
    except Exception:
        logger.exception("Failed to read chart_days; assuming 30.")
        return 30


def _day_str(target: date) -> str:
    """Format a date as YYYY-MM-DD for SQLite date() comparison."""
    return target.isoformat()


def compute_live_stats_for_date(db: Session, target_date: date) -> dict:
    """Derive funnel counters for one day from live lead/queue timestamps.

    Two round trips total: one conditional aggregate over ``GroupLead``,
    one count over ``GroupPostQueue``.
    """
    day = _day_str(target_date)
    # One conditional aggregate over GroupLead: capture day uses
    # created_at; M1/M2/converted/revenue use their own event timestamps,
    # so leads captured on other days still count when events land here.
    agg = (
        db.query(
            func.sum(
                case((func.date(GroupLead.created_at) == day, 1), else_=0)
            ).label("leads_captured"),
            func.sum(
                case((func.date(GroupLead.step1_sent_at) == day, 1), else_=0)
            ).label("m1_sent"),
            func.sum(
                case((func.date(GroupLead.step2_sent_at) == day, 1), else_=0)
            ).label("m2_sent"),
            func.sum(
                case(
                    (
                        (GroupLead.status == "converted")
                        & (func.date(GroupLead.updated_at) == day),
                        1,
                    ),
                    else_=0,
                )
            ).label("converted"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (GroupLead.status == "converted")
                            & (func.date(GroupLead.updated_at) == day),
                            GroupLead.conversion_value,
                        ),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("revenue"),
        ).one()
    )
    posts = (
        db.query(func.count(GroupPostQueue.id))
        .filter(func.date(GroupPostQueue.posted_at) == day)
        .scalar()
        or 0
    )
    return {
        "leads_captured": int(agg.leads_captured or 0),
        "m1_sent": int(agg.m1_sent or 0),
        "m2_sent": int(agg.m2_sent or 0),
        "converted": int(agg.converted or 0),
        "revenue": round(float(agg.revenue or 0.0), 2),
        "posts_published": int(posts),
    }


def _validate_stat_payload(payload: dict) -> dict:
    """Coerce + validate provided stat fields; raise ValueError on violation.

    Only keys present in ``payload`` are returned: inserts rely on column
    defaults for the rest, updates leave stored values untouched.
    """
    cleaned: dict = {}
    for field in STAT_NUMERIC_FIELDS:
        if field not in payload or payload[field] is None:
            continue
        try:
            number = int(payload[field])
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be an integer >= 0.")
        if number < 0:
            raise ValueError(f"{field} must be an integer >= 0.")
        cleaned[field] = number
    if "revenue" in payload and payload["revenue"] is not None:
        try:
            revenue = float(payload["revenue"])
        except (TypeError, ValueError):
            raise ValueError("revenue must be a number >= 0.")
        if revenue < 0:
            raise ValueError("revenue must be a number >= 0.")
        cleaned["revenue"] = round(revenue, 2)
    if payload.get("notes") is not None:
        cleaned["notes"] = str(payload["notes"])[:2000]
    return cleaned


def upsert_daily_stat(db: Session, stat_date: date, payload: dict) -> GroupStats:
    """Insert or update the snapshot for ``stat_date``, atomically.

    Explicit payload values always win. Missing funnel fields auto-fill
    from live data when ``stats_auto_compute`` is on. Manual-only fields
    (member counts, comments, notes) are never auto-zeroed: on update
    they keep the stored value unless the payload says otherwise.
    """
    if not isinstance(stat_date, date) or isinstance(stat_date, datetime):
        raise ValueError("stat_date must be a YYYY-MM-DD date.")
    if stat_date > _today_utc():
        raise ValueError("stat_date cannot be in the future.")
    explicit = {k: v for k, v in (payload or {}).items() if v is not None}
    auto = is_auto_compute(db)
    live: dict = {}
    if auto:
        try:
            live = compute_live_stats_for_date(db, stat_date)
        except Exception:
            logger.exception("Live stat auto-compute failed; using zeros.")
            live = {}
    auto_fields = ("posts_published", "leads_captured", "m1_sent",
                   "m2_sent", "converted", "revenue")
    # Explicit payload values always win. Missing auto fields fill from
    # live data — monotonically on update (max(stored, live)) so a manual
    # entry above the live count is never clobbered by a later auto-fill,
    # while live counters still grow through the day.
    merged = dict(explicit)
    existing = db.query(GroupStats).filter(GroupStats.stat_date == stat_date).first()
    for field in auto_fields:
        if field in merged or field not in live:
            continue
        if existing is None:
            merged[field] = live[field]
        else:
            stored = getattr(existing, field, 0) or 0
            merged[field] = max(float(stored), float(live[field]))
            if field != "revenue":
                merged[field] = int(merged[field])
    cleaned = _validate_stat_payload(merged)

    def _apply(row: GroupStats, values: dict) -> None:
        for key, value in values.items():
            setattr(row, key, value)

    try:
        row = existing
        if row is None:
            row = GroupStats(stat_date=stat_date)
            db.add(row)
        _apply(row, cleaned)
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        # Lost a race with a concurrent insert: fall back to UPDATE.
        db.rollback()
        logger.warning("Stat upsert raced for %s; retrying as update.", stat_date)
        try:
            row = db.query(GroupStats).filter(GroupStats.stat_date == stat_date).first()
            if row is None:
                raise ValueError(f"Daily stat for {stat_date} could not be saved.")
            _apply(row, cleaned)
            db.commit()
            db.refresh(row)
            return row
        except Exception:
            db.rollback()
            logger.exception("Stat upsert retry failed for %s.", stat_date)
            raise
    except Exception:
        db.rollback()
        logger.exception("Stat upsert failed for %s.", stat_date)
        raise


def row_to_dict(row: GroupStats) -> dict:
    """Serialize a GroupStats row to a plain dict."""
    return {
        "id": row.id,
        "stat_date": row.stat_date.isoformat(),
        "member_count": int(row.member_count or 0),
        "new_members": int(row.new_members or 0),
        "posts_published": int(row.posts_published or 0),
        "comments_received": int(row.comments_received or 0),
        "leads_captured": int(row.leads_captured or 0),
        "m1_sent": int(row.m1_sent or 0),
        "m2_sent": int(row.m2_sent or 0),
        "converted": int(row.converted or 0),
        "revenue": round(float(row.revenue or 0.0), 2),
        "notes": row.notes,
    }


def _zero_day(target: date) -> dict:
    """Zero-filled placeholder for a day with no snapshot row."""
    return {
        "id": None,
        "stat_date": target.isoformat(),
        "member_count": 0,
        "new_members": 0,
        "posts_published": 0,
        "comments_received": 0,
        "leads_captured": 0,
        "m1_sent": 0,
        "m2_sent": 0,
        "converted": 0,
        "revenue": 0.0,
        "notes": None,
    }


def get_stats_range(db: Session, start: date, end: date) -> list[dict]:
    """Return ascending daily rows for [start, end], zero-filling gaps.

    Single query + in-memory fill. No N+1.
    """
    if start > end:
        raise ValueError("start must be on or before end.")
    rows = (
        db.query(GroupStats)
        .filter(GroupStats.stat_date >= start, GroupStats.stat_date <= end)
        .order_by(GroupStats.stat_date.asc())
        .all()
    )
    by_date = {row.stat_date: row for row in rows}
    result: list[dict] = []
    current = start
    while current <= end:
        row = by_date.get(current)
        result.append(row_to_dict(row) if row is not None else _zero_day(current))
        current += timedelta(days=1)
    return result


def _week_bounds(today: date, week_start: str) -> tuple[date, date, date]:
    """Return (this_monday_or_sunday, last_week_start, last_week_end)."""
    weekday = today.weekday()  # Monday == 0
    if week_start == "sunday":
        shift = (weekday + 1) % 7
    else:
        shift = weekday
    this_start = today - timedelta(days=shift)
    last_end = this_start - timedelta(days=1)
    last_start = last_end - timedelta(days=6)
    return this_start, last_start, last_end


def get_weekly_digest(db: Session, week_start: str = "monday") -> dict:
    """Compare this week vs last week across all digest metrics."""
    mode = "sunday" if (week_start or "").strip().lower() == "sunday" else "monday"
    today = _today_utc()
    this_start, last_start, last_end = _week_bounds(today, mode)
    rows = (
        db.query(GroupStats)
        .filter(GroupStats.stat_date >= last_start, GroupStats.stat_date <= today)
        .order_by(GroupStats.stat_date.asc())
        .all()
    )
    this_rows = [r for r in rows if r.stat_date >= this_start]
    last_rows = [r for r in rows if r.stat_date < this_start]

    def _sums(members: list[GroupStats]) -> dict:
        totals = {key: 0 for key in DIGEST_KEYS if key != "member_count"}
        totals["member_count"] = 0
        for row in members:
            for key in DIGEST_KEYS:
                if key == "member_count":
                    continue
                value = getattr(row, key, 0) or 0
                totals[key] += float(value) if key == "revenue" else int(value)
        # member_count is a gauge: latest row in the span wins.
        if members:
            totals["member_count"] = int(members[-1].member_count or 0)
        totals["revenue"] = round(float(totals["revenue"]), 2)
        return totals

    this_week = _sums(this_rows)
    last_week = _sums(last_rows)
    delta: dict = {}
    trend: dict = {}
    for key in DIGEST_KEYS:
        new_value = float(this_week[key])
        old_value = float(last_week[key])
        if key == "member_count":
            # Gauge delta: absolute change, not a rate over summed days.
            change = new_value - old_value
            delta[key] = round(change, 2)
            trend[key] = "up" if change > 0 else "down" if change < 0 else "flat"
            continue
        if old_value == 0:
            delta[key] = None
            trend[key] = "up" if new_value > 0 else "flat"
        else:
            pct = (new_value - old_value) / abs(old_value) * 100.0
            delta[key] = round(pct, 1)
            trend[key] = "up" if pct > 0 else "down" if pct < 0 else "flat"
    return {
        "this_week": this_week,
        "last_week": last_week,
        "delta": delta,
        "trend": trend,
        "week_start": mode,
        "this_week_start": this_start.isoformat(),
        "last_week_start": last_start.isoformat(),
    }


def get_template_performance(db: Session, days: int = 30) -> list[dict]:
    """Per-template funnel rollup. One query (UNION + LEFT JOIN + GROUP BY)."""
    from sqlalchemy import text

    window = max(1, min(365, int(days)))
    cutoff = (_today_utc() - timedelta(days=window - 1)).isoformat()
    sql = text(
        'WITH names AS ('
        ' SELECT DISTINCT "template_name" AS name FROM "group_post_queue"'
        ' WHERE "template_name" IS NOT NULL'
        ' UNION'
        ' SELECT DISTINCT "source_template" AS name FROM "group_leads"'
        ' WHERE "source_template" IS NOT NULL'
        ') SELECT t.name AS template_name,'
        ' COUNT(DISTINCT q."id") AS posts_queued,'
        ' COUNT(DISTINCT CASE WHEN q."copied_at" IS NOT NULL THEN q."id" END) AS posts_copied,'
        ' COUNT(DISTINCT CASE WHEN q."posted_at" IS NOT NULL THEN q."id" END) AS posts_posted,'
        ' COUNT(DISTINCT l."id") AS leads_captured,'
        ' COUNT(DISTINCT CASE WHEN l."status" = \'converted\' THEN l."id" END) AS converted,'
        ' COALESCE(SUM(CASE WHEN l."status" = \'converted\''
        ' THEN l."conversion_value" ELSE 0.0 END), 0.0) AS revenue'
        ' FROM names t'
        ' LEFT JOIN "group_post_queue" q ON q."template_name" = t.name'
        ' LEFT JOIN "group_leads" l ON l."source_template" = t.name'
        ' AND date(l."created_at") >= :cutoff'
        ' GROUP BY t.name ORDER BY revenue DESC LIMIT 20'
    )
    result = []
    for row in db.execute(sql, {"cutoff": cutoff}).mappings().all():
        leads = int(row["leads_captured"] or 0)
        converted = int(row["converted"] or 0)
        result.append({
            "template_name": row["template_name"],
            "posts_queued": int(row["posts_queued"] or 0),
            "posts_copied": int(row["posts_copied"] or 0),
            "posts_posted": int(row["posts_posted"] or 0),
            "leads_captured": leads,
            "converted": converted,
            "revenue": round(float(row["revenue"] or 0.0), 2),
            "conversion_rate": round(converted / leads, 4) if leads else 0.0,
        })
    return result
