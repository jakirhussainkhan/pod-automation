"""Dashboard statistics response model."""

from pydantic import BaseModel

from app.schemas.activity_log import ActivityLogRead


class DashboardStats(BaseModel):
    """Aggregated dashboard statistics."""

    total_products: int
    active_products: int
    total_posts: int
    posts_by_status: dict[str, int]
    posts_scheduled_next_24h: int
    posts_published_last_7_days: int
    ai_generations_total: int
    ai_generations_failed: int
    recent_activity: list[ActivityLogRead]
