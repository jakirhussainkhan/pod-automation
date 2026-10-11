"""Activity log API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.routers.deps import require_destructive_confirmation
from app.schemas.activity_log import ActivityLogRead
from app.schemas.common import Page
from app.services import ai_generation_service, log_service

router: APIRouter = APIRouter(prefix="/api/logs", tags=["logs"])


class RestoreLogsRequest(BaseModel):
    """Request body for restoring soft-deleted rows from log snapshots."""

    log_ids: list[int]


@router.post("/restore", response_model=dict)
def restore_logs_endpoint(
    data: RestoreLogsRequest, db: Session = Depends(get_db)
) -> dict:
    """Restore soft-deleted products/posts/demo data from log snapshots."""
    unique_ids = sorted({item for item in (data.log_ids or []) if isinstance(item, int) and item > 0})
    if not unique_ids:
        raise HTTPException(
            status_code=422, detail="Provide at least one positive log id."
        )
    if len(unique_ids) > 100:
        raise HTTPException(status_code=422, detail="Too many ids (max 100).")
    return log_service.restore_logs(db, unique_ids)


@router.delete("/clear")
def clear_logs_endpoint(
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> dict:
    """Delete all activity log and AI generation entries."""
    deleted_logs = log_service.clear_logs(db)
    deleted_generations = ai_generation_service.clear_generations(db)
    return {
        "deleted": deleted_logs + deleted_generations,
        "deleted_logs": deleted_logs,
        "deleted_generations": deleted_generations,
    }


@router.get("", response_model=Page[ActivityLogRead])
def list_logs_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    level: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    """List activity log entries with pagination and level filter."""
    items = log_service.list_logs(db, skip=skip, limit=limit, level=level)
    total = log_service.count_logs(db, level=level)
    return {"items": items, "total": total, "skip": skip, "limit": limit}
