"""Dashboard statistics API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.dashboard import DashboardStats
from app.services import post_service

router: APIRouter = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats_endpoint(db: Session = Depends(get_db)) -> DashboardStats:
    """Return aggregated dashboard statistics."""
    return DashboardStats(**post_service.get_dashboard_stats(db))
