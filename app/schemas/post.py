"""Pydantic schemas for posts."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import PostStatus


class PostBase(BaseModel):
    """Shared post fields."""

    product_id: Optional[int] = None
    caption: str = Field(min_length=1)
    hashtags: list[str] = Field(default_factory=list)
    image_url: Optional[str] = Field(default=None, max_length=500)
    status: PostStatus = PostStatus.draft
    scheduled_at: Optional[datetime] = None

    @field_validator("caption")
    @classmethod
    def _caption_not_blank(cls, value: str) -> str:
        """Ensure caption is not blank after stripping."""
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class PostCreate(PostBase):
    """Schema for creating a post."""


class PostUpdate(BaseModel):
    """Schema for updating a post; all fields optional."""

    product_id: Optional[int] = None
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    image_url: Optional[str] = Field(default=None, max_length=500)
    status: Optional[PostStatus] = None
    scheduled_at: Optional[datetime] = None

    @field_validator("caption")
    @classmethod
    def _caption_not_blank_if_provided(cls, value: Optional[str]) -> Optional[str]:
        """Ensure provided caption is not blank."""
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class PostRead(PostBase):
    """Schema for reading a post."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    published_at: Optional[datetime] = None
    facebook_post_id: Optional[str] = None
    error_message: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    publish_attempts: int = 0
    last_attempt_at: Optional[datetime] = None
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime
