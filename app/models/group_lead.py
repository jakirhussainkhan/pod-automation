"""GroupLead ORM model for the Facebook Group DM funnel."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class GroupLead(Base):
    """A Facebook Group commenter tracked through the 2-step DM funnel.

    Status flow: ``unsent`` -> ``step1_sent`` -> ``step2_sent`` -> ``converted``.
    ``replied`` marks that the user answered Message 1 (safe to send Message 2).
    """

    __tablename__ = "group_leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, default="group_member")
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    intent: Mapped[str] = mapped_column(String(10), default="low", nullable=False, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message1: Mapped[str] = mapped_column(Text, nullable=False, default="")
    message2: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), default="unsent", nullable=False, index=True)
    user_profile_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    conversion_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0", index=True
    )
    step1_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    step2_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    assigned_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fb_accounts.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    follow_up_due_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    follow_up_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    follow_up_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    reply_state: Mapped[str] = mapped_column(
        String(10), default="unknown", nullable=False, server_default="unknown", index=True
    )
    source_template: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
