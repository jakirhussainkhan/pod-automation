"""Pydantic schemas for AI content generation."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.ai.prompts import ALLOWED_TONES, normalize_tone


class GeneratePostRequest(BaseModel):
    """Request to generate a full post for a product."""

    product_id: int
    tone: str = "friendly"

    @field_validator("tone")
    @classmethod
    def _normalize_tone(cls, value: str) -> str:
        """Fall back to 'friendly' for unknown tones."""
        return normalize_tone(value)


class RegenerateCaptionRequest(BaseModel):
    """Request to regenerate a post caption with a given tone."""

    tone: str = "friendly"

    @field_validator("tone")
    @classmethod
    def _normalize_tone(cls, value: str) -> str:
        """Fall back to 'friendly' for unknown tones."""
        return normalize_tone(value)


class VariationsRequest(BaseModel):
    """Request for multiple post variations of a product."""

    count: int = Field(default=3, ge=2, le=5)


class GeneratedContent(BaseModel):
    """AI-generated post content with provenance."""

    caption: str
    hashtags: list[str]
    call_to_action: str = ""
    image_idea: str = ""
    provider: str
    model: str


class AIStatusResponse(BaseModel):
    """AI provider configuration status (never includes API keys)."""

    primary_provider: str
    fallback_provider: Optional[str] = None
    mock_mode: bool
    groq_configured: bool
    openai_configured: bool


__all__ = [
    "ALLOWED_TONES",
    "GeneratePostRequest",
    "RegenerateCaptionRequest",
    "VariationsRequest",
    "GeneratedContent",
    "AIStatusResponse",
]
