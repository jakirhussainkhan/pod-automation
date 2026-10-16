"""FbAccount ORM model for per-account DM rate limiting + ghost personas."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


PERSONA_TONES: tuple[str, ...] = ("casual", "enthusiast", "veteran", "young_gun")
"""Allowed ghost-persona voice tones (validated in account_service)."""

NICHE_FOCUS_VALUES: tuple[str, ...] = ("mustang", "harley", "jdm", "muscle", "mixed")
"""Allowed niche focuses (validated in account_service)."""

ACCOUNT_HEALTH_VALUES: tuple[str, ...] = ("healthy", "warned", "restricted", "banned")
"""Allowed account health states."""


class FbAccount(Base):
    """A Facebook account with hourly/daily DM quota counters.

    Counters reset lazily on read/write: hourly when
    ``last_hourly_reset_at`` is >1h old, daily when
    ``last_daily_reset_at`` is >24h old (see dm_safety service).

    Phase 5 adds the ghost-persona layer (handle, persona_*, niche
    focus), health tracking (health_status, warnings, restriction
    windows) and lifetime counters for per-account analytics.
    ``handle`` uniqueness is enforced by a partial unique index
    (``WHERE handle IS NOT NULL``) plus a service-layer check, because
    SQLite forbids UNIQUE inside ``ALTER TABLE ADD COLUMN``.
    """

    __tablename__ = "fb_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Default Account")
    profile_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    daily_dm_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    hourly_dm_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    last_hourly_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_daily_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    daily_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False, server_default="20")
    hourly_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False, server_default="10")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1", index=True
    )
    handle: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, default=None, index=True
    )
    persona_name: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, default=None
    )
    persona_avatar_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )
    persona_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    persona_tone: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )
    niche_focus: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )
    health_status: Mapped[str] = mapped_column(
        String(20), default="healthy", nullable=False, server_default="healthy", index=True
    )
    health_note: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )
    restricted_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    warnings_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    total_dms_sent: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    total_converted: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    total_revenue: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, server_default="0.0"
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=100, nullable=False, server_default="100"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AccountGroupBlocked(Base):
    """Collision-prevention entry: an account kept out of one group.

    Rows are advisory, not permanent bans: ``is_account_blocked_from_group``
    only honors rows newer than the collision window, so old entries
    expire naturally without cleanup jobs.
    """

    __tablename__ = "account_groups_blocked"
    __table_args__ = (
        UniqueConstraint("account_id", "group_name", name="uq_account_group"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("fb_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
