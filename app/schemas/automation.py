"""Pydantic schema for Automation scheduler status."""

from typing import Any, Optional

from pydantic import BaseModel


class AutomationStatus(BaseModel):
    """Automation scheduler status snapshot."""

    running: bool
    enabled: bool
    interval_seconds: int
    last_run_at: Optional[str] = None
    last_run_result: dict[str, Any] = {}
    next_run_at: Optional[str] = None
