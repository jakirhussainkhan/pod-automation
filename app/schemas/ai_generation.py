"""Pydantic schema for AI generations."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AIGenerationRead(BaseModel):
    """Schema for reading an AI generation record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: Optional[int] = None
    prompt: str
    response: str
    provider: str
    model: str
    tokens_used: Optional[int] = None
    success: bool
    created_at: datetime
