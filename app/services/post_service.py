"""CRUD service for posts."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.models import PostStatus
from app.models.activity_log import ActivityLog
from app.models.ai_generation import AIGeneration
from app.models.post import Post
from app.models.product import Product
from app.schemas.post import PostCreate, PostUpdate


def create_post(db: Session, data: PostCreate) -> Post:
    """Create a post and commit it."""
    post = Post(**data.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def get_post(db: Session, post_id: int) -> Optional[Post]:
    """Return a post by id, or None when not found."""
    return db.get(Post, post_id)


def list_posts(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: Optional[str | PostStatus] = None,
    product_id: Optional[int] = None,
) -> list[Post]:
    """List posts with optional status and product filters."""
    query = db.query(Post)
    if status:
        status_value = status.value if isinstance(status, PostStatus) else status
        query = query.filter(Post.status == status_value)
    if product_id is not None:
        query = query.filter(Post.product_id == product_id)
    return query.order_by(Post.id.desc()).offset(skip).limit(limit).all()


def update_post(db: Session, post_id: int, data: PostUpdate) -> Optional[Post]:
    """Update a post; return None when missing, refuse published posts."""
    post = db.get(Post, post_id)
    if post is None:
        return None
    if post.status == PostStatus.published.value:
        raise ValueError("Published posts cannot be modified.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    db.commit()
    db.refresh(post)
    return post


def delete_post(db: Session, post_id: int) -> bool:
    """Delete a post in any status; return False when missing."""
    post = db.get(Post, post_id)
    if post is None:
        return False
    db.delete(post)
    db.commit()
    return True


def bulk_delete_posts(
    db: Session,
    ids: Optional[list[int]] = None,
    delete_all: bool = False,
    status: Optional[str] = None,
) -> int:
    """Delete many posts at once; return the number deleted.

    Either an explicit id list, or delete_all (optionally scoped to a status).
    Published posts are deletable here — deletion only removes the local
    record, it never unpublishes anything on Facebook.
    """
    query = db.query(Post)
    if delete_all:
        if status:
            query = query.filter(Post.status == status)
    elif ids:
        query = query.filter(Post.id.in_(ids))
    else:
        return 0
    rows = query.all()
    count = len(rows)
    for post in rows:
        db.delete(post)
    if count:
        db.commit()
    return count


def count_posts_by_status(db: Session) -> dict[str, int]:
    """Return a count for every PostStatus, including zeros."""
    rows = db.query(Post.status, func.count(Post.id)).group_by(Post.status).all()
    counts: dict[str, int] = {status.value: 0 for status in PostStatus}
    for status_value, count in rows:
        counts[str(status_value)] = int(count)
    return counts


def mark_post_published(
    db: Session, post_id: int, facebook_post_id: str
) -> Optional[Post]:
    """Mark a post as published; return None when not found."""
    from datetime import timezone

    post = db.get(Post, post_id)
    if post is None:
        return None
    post.status = PostStatus.published.value
    post.facebook_post_id = facebook_post_id
    post.published_at = datetime.now(timezone.utc)
    post.error_message = None
    db.commit()
    db.refresh(post)
    return post


def mark_post_failed(db: Session, post_id: int, error_message: str) -> Optional[Post]:
    """Mark a post as failed; return None when not found."""
    post = db.get(Post, post_id)
    if post is None:
        return None
    post.status = PostStatus.failed.value
    post.error_message = error_message
    db.commit()
    db.refresh(post)
    return post


def get_due_scheduled_posts(
    db: Session, now: datetime, limit: Optional[int] = None
) -> list[Post]:
    """Return scheduled posts whose scheduled_at is at or before now."""
    query = (
        db.query(Post)
        .filter(Post.status == PostStatus.scheduled.value)
        .filter(Post.scheduled_at.is_not(None))
        .filter(Post.scheduled_at <= now)
        .order_by(Post.scheduled_at.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


# A publish left in 'publishing' longer than this is presumed interrupted
# (process crash / hard timeout) and is released back to 'failed'.
_STALE_PUBLISHING_SECONDS = 900


def reclaim_stale_publishing(
    db: Session, stale_seconds: int = _STALE_PUBLISHING_SECONDS
) -> int:
    """Release posts stuck in 'publishing' back to 'failed'.

    Prevents an interrupted publish (crash or timeout between the claim and the
    final status write) from leaving a post claimed forever. The post becomes
    retryable, subject to PUBLISH_MAX_ATTEMPTS. Returns the count reclaimed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
    result = db.execute(
        update(Post)
        .where(
            Post.status == PostStatus.publishing.value,
            (Post.last_attempt_at.is_(None)) | (Post.last_attempt_at < cutoff),
        )
        .values(
            status=PostStatus.failed.value,
            error_message=(
                "Publishing was interrupted; verify on Facebook before retrying."
            ),
        )
    )
    db.commit()
    return int(result.rowcount or 0)


def count_posts(
    db: Session,
    status: Optional[str | PostStatus] = None,
    product_id: Optional[int] = None,
) -> int:
    """Count posts with optional status and product filters."""
    query = db.query(func.count(Post.id))
    if status:
        status_value = status.value if isinstance(status, PostStatus) else status
        query = query.filter(Post.status == status_value)
    if product_id is not None:
        query = query.filter(Post.product_id == product_id)
    return query.scalar() or 0


def schedule_post(db: Session, post_id: int, scheduled_at: datetime) -> Optional[Post]:
    """Schedule a draft/failed post for a future UTC time."""
    post = db.get(Post, post_id)
    if post is None:
        return None
    if post.status not in (PostStatus.draft.value, PostStatus.failed.value):
        raise ValueError("Only draft or failed posts can be scheduled.")
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    if scheduled_at <= datetime.now(timezone.utc):
        raise ValueError("scheduled_at must be in the future.")
    post.scheduled_at = scheduled_at
    post.status = PostStatus.scheduled.value
    post.error_message = None
    db.commit()
    db.refresh(post)
    return post


def unschedule_post(db: Session, post_id: int) -> Optional[Post]:
    """Return a scheduled post to draft and clear its scheduled time."""
    post = db.get(Post, post_id)
    if post is None:
        return None
    if post.status != PostStatus.scheduled.value:
        raise ValueError("Only scheduled posts can be unscheduled.")
    post.status = PostStatus.draft.value
    post.scheduled_at = None
    db.commit()
    db.refresh(post)
    return post


def duplicate_post(db: Session, post_id: int) -> Optional[Post]:
    """Create a new draft copy of a post without scheduling metadata."""
    post = db.get(Post, post_id)
    if post is None:
        return None
    copy = Post(
        product_id=post.product_id,
        caption=post.caption,
        hashtags=list(post.hashtags or []),
        image_url=post.image_url,
        status=PostStatus.draft.value,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


def get_dashboard_stats(db: Session) -> dict:
    """Aggregate dashboard statistics across products, posts, AI and logs."""
    now = datetime.now(timezone.utc)
    total_products = db.query(func.count(Product.id)).scalar() or 0
    active_products = (
        db.query(func.count(Product.id))
        .filter(Product.status == "active")
        .scalar()
        or 0
    )
    total_posts = db.query(func.count(Post.id)).scalar() or 0
    posts_by_status = count_posts_by_status(db)
    scheduled_24h = (
        db.query(func.count(Post.id))
        .filter(Post.status == PostStatus.scheduled.value)
        .filter(Post.scheduled_at.is_not(None))
        .filter(Post.scheduled_at >= now)
        .filter(Post.scheduled_at <= now + timedelta(hours=24))
        .scalar()
        or 0
    )
    published_7d = (
        db.query(func.count(Post.id))
        .filter(Post.status == PostStatus.published.value)
        .filter(Post.published_at.is_not(None))
        .filter(Post.published_at >= now - timedelta(days=7))
        .scalar()
        or 0
    )
    ai_total = db.query(func.count(AIGeneration.id)).scalar() or 0
    ai_failed = (
        db.query(func.count(AIGeneration.id))
        .filter(AIGeneration.success.is_(False))
        .scalar()
        or 0
    )
    recent = (
        db.query(ActivityLog).order_by(ActivityLog.id.desc()).limit(10).all()
    )
    recent_activity = [
        {
            "id": entry.id,
            "level": entry.level,
            "event_type": entry.event_type,
            "message": entry.message,
            "post_id": entry.post_id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in recent
    ]
    return {
        "total_products": total_products,
        "active_products": active_products,
        "total_posts": total_posts,
        "posts_by_status": posts_by_status,
        "posts_scheduled_next_24h": scheduled_24h,
        "posts_published_last_7_days": published_7d,
        "ai_generations_total": ai_total,
        "ai_generations_failed": ai_failed,
        "recent_activity": recent_activity,
    }
