"""DbBackup ORM model for SQLite backup snapshots."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class DbBackup(Base):
    """A recorded SQLite backup file (scheduled or manual).

    Files live in ``data/backups/``; rows track status so failed runs
    stay visible. Restore always snapshots a pre-restore backup first.
    """

    __tablename__ = "db_backups"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), default="ok", nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class AiUsage(Base):
    """One metered AI provider call (cost + success tracking).

    Token split is approximate: providers report a single total, which
    is booked to ``tokens_out`` (see ai_usage_service).
    """

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_provider_created", "provider", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    call_type: Mapped[str] = mapped_column(String(20), default="other", nullable=False, index=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
