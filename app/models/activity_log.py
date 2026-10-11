"""ActivityLog ORM model."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# Event types whose log entry carries a JSON snapshot that can be restored.
RESTORABLE_LOG_EVENTS: frozenset[str] = frozenset(
    {
        "product_deleted",
        "post_deleted",
        "posts_bulk_deleted",
        "dummy_data_cleared",
    }
)
"""Deletion event types eligible for soft-delete restore."""


class ActivityLog(Base):
    """Append-only activity log entry for dashboard events."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(10), default="INFO", nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    post_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Soft-delete support: JSON snapshot of the deleted rows + restore flag.
    # Snapshot shapes:
    #   product_deleted: {"product": {...}, "posts": [...]}
    #   post_deleted: {"post": {...}}
    #   posts_bulk_deleted: {"posts": [...]}
    #   dummy_data_cleared: {"products": [...], "posts": [...],
    #                        "group_leads": [...], "group_post_queue": [...]}
    snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, default=None
    )
    entity_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )
    restored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    @property
    def restorable(self) -> bool:
        """Whether this entry represents a restorable deletion event."""
        return self.event_type in RESTORABLE_LOG_EVENTS

    @property
    def has_snapshot(self) -> bool:
        """Whether a JSON snapshot is stored for restore."""
        return bool(self.snapshot)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
