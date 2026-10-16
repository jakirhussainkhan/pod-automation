"""Pydantic schemas for the Group Lead & DM Funnel."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

LEAD_STATUSES: tuple[str, ...] = ("unsent", "step1_sent", "step2_sent", "replied", "converted", "follow_up_sent")
LEAD_INTENTS: tuple[str, ...] = ("high", "medium", "low")
REPLY_STATES: tuple[str, ...] = ("unknown", "replied", "no_reply", "bounced")


class ClassifyCommentRequest(BaseModel):
    """Request to classify a raw group comment."""

    comment_text: str = Field(min_length=1, max_length=2000)
    username: str = Field(default="group_member", max_length=120)
    group_name: Optional[str] = Field(default=None, max_length=200)


class ClassifyCommentResponse(BaseModel):
    """Intent classification result with matched signals."""

    intent: str
    confidence: float
    signals: list[str]
    message1: str = ""
    message2: str = ""


class GroupLeadCreate(BaseModel):
    """Request to create (and auto-score) a group lead."""

    comment_text: str = Field(min_length=1, max_length=2000)
    username: str = Field(default="group_member", max_length=120)
    group_name: Optional[str] = Field(default=None, max_length=200)
    product_id: Optional[int] = None
    user_profile_link: Optional[str] = Field(default=None, max_length=500)
    conversion_value: float = Field(default=0.0, ge=0.0)
    source_template: Optional[str] = Field(default=None, max_length=60)


class GroupLeadUpdate(BaseModel):
    """Request to update a lead's funnel status, profile link, or revenue."""

    status: Optional[str] = Field(default=None, pattern="^(unsent|step1_sent|step2_sent|replied|converted|follow_up_sent)$")
    user_profile_link: Optional[str] = Field(default=None, max_length=500)
    conversion_value: Optional[float] = Field(default=None, ge=0.0)
    group_name: Optional[str] = Field(default=None, max_length=200)
    assigned_account_id: Optional[int] = Field(default=None, ge=1)


class GroupLeadRead(BaseModel):
    """Serialized group lead with funnel state."""

    id: int
    username: str
    comment_text: str
    group_name: Optional[str] = None
    intent: str
    product_id: Optional[int] = None
    message1: str
    message2: str
    status: str
    user_profile_link: Optional[str] = None
    conversion_value: float = 0.0
    is_demo: bool = False
    step1_sent_at: Optional[datetime] = None
    step2_sent_at: Optional[datetime] = None
    assigned_account_id: Optional[int] = None
    last_checked_at: Optional[datetime] = None
    follow_up_due_at: Optional[datetime] = None
    follow_up_sent_at: Optional[datetime] = None
    follow_up_count: int = 0
    reply_state: str = "unknown"
    source_template: Optional[str] = None
    urgency: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CadenceResponse(BaseModel):
    """Randomized anti-spam safety delay."""

    delay_seconds: int
    delay_label: str
    min_seconds: int = 180
    max_seconds: int = 300


class GroupPostRequest(BaseModel):
    """Request to generate a psychology-driven link-free group post."""

    niche: str = Field(default="car", max_length=40)
    template: str = Field(default="show_your_ride", max_length=60)
    subculture: str = Field(default="auto", max_length=40)
    trigger: str = Field(default="auto", max_length=40)


class MarkReplyRequest(BaseModel):
    """Manual reply-check outcome after the user reads the DM thread."""

    reply_state: str = Field(pattern="^(replied|no_reply|bounced)$")


class BulkMarkReplyRequest(BaseModel):
    """Bulk reply-check outcome for up to 100 leads in one call."""

    ids: list[int] = Field(min_length=1, max_length=100)
    reply_state: str = Field(pattern="^(replied|no_reply|bounced)$")


__all__ = [
    "LEAD_STATUSES",
    "LEAD_INTENTS",
    "REPLY_STATES",
    "CadenceResponse",
    "ClassifyCommentRequest",
    "ClassifyCommentResponse",
    "GroupLeadCreate",
    "GroupLeadRead",
    "GroupLeadUpdate",
    "GroupPostRequest",
    "MarkReplyRequest",
    "BulkMarkReplyRequest",
]
