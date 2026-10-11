"""Pydantic schemas for the Group Post Queue and bulk comment capture."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QueueBatchRequest(BaseModel):
    """Request to auto-generate a batch of distinct queued group posts."""

    niche: str = Field(default="mixed", max_length=20)
    count: int = Field(default=5, ge=1, le=5)


class QueueUpdate(BaseModel):
    """Request to edit a queued post's caption or change its status."""

    caption: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    status: Optional[str] = Field(default=None, pattern="^(queued|posted)$")


class QueueItemRead(BaseModel):
    """Serialized queued group post."""

    id: int
    niche: str
    subculture: str
    template: str
    trigger: str
    caption: str
    hashtags: list[str]
    call_to_action: str
    image_idea: str
    status: str
    is_demo: bool = False
    copied_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    template_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BulkParseRequest(BaseModel):
    """Request to parse many raw group comments at once (one per line)."""

    text: str = Field(min_length=1, max_length=20000)
    group_name: Optional[str] = Field(default=None, max_length=200)
    product_id: Optional[int] = None


class BulkParseSkipped(BaseModel):
    """A parsed comment that was classified but NOT saved (not high intent)."""

    username: str
    comment_text: str
    intent: str
    confidence: float


class BulkParseResponse(BaseModel):
    """Bulk parse result: saved high-intent leads + skipped comments."""

    total_parsed: int
    saved_high: int
    skipped: list[BulkParseSkipped]
    lead_ids: list[int]


class RevenueStats(BaseModel):
    """Revenue totals from converted group DM leads."""

    total_revenue: float
    converted_count: int
    average_value: float


__all__ = [
    "BulkParseRequest",
    "BulkParseResponse",
    "BulkParseSkipped",
    "QueueBatchRequest",
    "QueueItemRead",
    "QueueUpdate",
    "RevenueStats",
]
