"""Post ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class Post(Base, TimestampMixin):
    """Facebook post linked to an optional product."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    facebook_post_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    publish_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0", index=True
    )
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    product: Mapped[Optional["Product"]] = relationship(
        "Product",
        back_populates="posts",
    )
