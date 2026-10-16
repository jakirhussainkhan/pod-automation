"""Pydantic schemas for posts."""

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import PostStatus


def _validate_image_url(value: Optional[str]) -> Optional[str]:
    """Accept only http(s) image URLs; reject blank/other schemes."""
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be a valid http(s) image URL")
    return cleaned


class PostBase(BaseModel):
    """Shared post fields."""

    product_id: Optional[int] = None
    caption: str = Field(min_length=1)
    hashtags: list[str] = Field(default_factory=list)
    image_url: Optional[str] = Field(default=None, max_length=500)
    scheduled_at: Optional[datetime] = None

    @field_validator("caption")
    @classmethod
    def _caption_not_blank(cls, value: str) -> str:
        """Ensure caption is not blank after stripping."""
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("image_url")
    @classmethod
    def _image_url_valid(cls, value: Optional[str]) -> Optional[str]:
        """Reject non-http(s) URLs (SSRF/validation hardening)."""
        return _validate_image_url(value)


class PostCreate(PostBase):
    """Schema for creating a post.

    A new post is always a draft — the client cannot forge a status such as
    ``published`` (that only happens through the publish pipeline).
    """


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

    @field_validator("image_url")
    @classmethod
    def _image_url_valid(cls, value: Optional[str]) -> Optional[str]:
        """Reject non-http(s) URLs (SSRF/validation hardening)."""
        return _validate_image_url(value)

    @field_validator("status")
    @classmethod
    def _status_not_reserved(cls, value: Optional[PostStatus]) -> Optional[PostStatus]:
        """Block directly setting pipeline-owned statuses."""
        if value in (PostStatus.published, PostStatus.publishing):
            raise ValueError(
                "status 'published'/'publishing' is managed by the publish pipeline"
            )
        return value


class PostRead(PostBase):
    """Schema for reading a post."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: PostStatus
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
