"""GroupPostQueue ORM model for the auto-generated daily post batch."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class GroupPostQueue(Base):
    """A pre-generated link-free group post waiting to be copied & posted.

    Status flow: ``queued`` -> ``posted``. Captions stay editable until posted.
    """

    __tablename__ = "group_post_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    niche: Mapped[str] = mapped_column(String(20), default="car", nullable=False)
    subculture: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)
    template: Mapped[str] = mapped_column(String(60), default="show_your_ride", nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    call_to_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_idea: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    copied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True
    )
    template_name: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, default=None, index=True
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )
