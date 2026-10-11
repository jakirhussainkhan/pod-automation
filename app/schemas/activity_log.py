"""Pydantic schema for activity logs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ActivityLogRead(BaseModel):
    """Schema for reading an activity log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    event_type: str
    message: str
    post_id: Optional[int] = None
    created_at: datetime
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    restored: bool = False
    restorable: bool = False
    has_snapshot: bool = False
