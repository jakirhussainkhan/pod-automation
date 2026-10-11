"""Pydantic schema for Facebook connection status."""

from typing import Optional

from pydantic import BaseModel


class FacebookStatus(BaseModel):
    """Facebook connection status without any secret values."""

    configured: bool
    dry_run: bool
    page_id: Optional[str] = None
    page_name: Optional[str] = None
    token_valid: Optional[bool] = None
    error: Optional[str] = None
