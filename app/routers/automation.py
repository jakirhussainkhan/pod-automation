"""Automation scheduler API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.automation import AutomationStatus
from app.services.scheduler import automation

router: APIRouter = APIRouter(prefix="/api/automation", tags=["automation"])


@router.get("/status", response_model=AutomationStatus)
async def automation_status_endpoint() -> AutomationStatus:
    """Return the Automation scheduler status snapshot."""
    return AutomationStatus(**automation.status())


@router.post("/run-now", response_model=dict)
async def automation_run_now_endpoint() -> dict:
    """Trigger one Automation tick on demand."""
    if automation.tick_running:
        raise HTTPException(status_code=409, detail="A tick is already running.")
    return await automation.run_once()


@router.post("/fill-queue", response_model=dict)
def automation_fill_queue_endpoint(db: Session = Depends(get_db)) -> dict:
    """Auto-schedule oldest drafts into posting-hour slots."""
    return automation.fill_queue(db)
