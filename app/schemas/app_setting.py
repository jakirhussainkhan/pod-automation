"""Pydantic schemas for app settings."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AppSettingRead(BaseModel):
    """Schema for reading an app setting."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: Optional[str] = None
    updated_at: datetime


class AppSettingUpdate(BaseModel):
    """Schema for updating an app setting value."""

    value: Optional[str] = Field(default=None)
