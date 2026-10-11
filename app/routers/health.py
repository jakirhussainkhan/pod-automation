"""Health-check API router."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings

router: APIRouter = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return service status, app metadata and current UTC timestamp."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "ai_provider": settings.AI_PROVIDER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
