"""GroupStats ORM model for daily group-health snapshots."""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class GroupStats(Base):
    """One manual (+auto-computed) health snapshot per calendar day.

    ``stat_date`` is unique: one row per YYYY-MM-DD. Funnel counters
    (leads/m1/m2/converted/revenue/posts) auto-fill from live
    ``GroupLead``/``GroupPostQueue`` timestamps when
    ``stats_auto_compute`` is on; member/comment counts are manual.
    """

    __tablename__ = "group_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    stat_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    new_members: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    posts_published: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    comments_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    leads_captured: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    m1_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    m2_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    converted: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, server_default="0.0")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


STAT_NUMERIC_FIELDS: tuple[str, ...] = (
    "member_count",
    "new_members",
    "posts_published",
    "comments_received",
    "leads_captured",
    "m1_sent",
    "m2_sent",
    "converted",
)
"""Integer counter fields on GroupStats (all must be >= 0)."""
