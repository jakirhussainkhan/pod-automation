"""Post API router."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.post import Post
from app.routers.deps import require_destructive_confirmation
from app.schemas.common import Page
from app.schemas.post import PostCreate, PostRead, PostUpdate
from app.services import log_service, post_service, product_service
from app.services.facebook.exceptions import (
    FacebookAuthError,
    FacebookConfigError,
    FacebookError,
    FacebookRateLimitError,
    redact_token_text,
)
from app.services.facebook.publisher import publish_post

router: APIRouter = APIRouter(prefix="/api/posts", tags=["posts"])


class SchedulePostRequest(BaseModel):
    """Request body for scheduling a post."""

    scheduled_at: datetime


class BulkDeleteRequest(BaseModel):
    """Request body for bulk post deletion."""

    ids: list[int] = []
    delete_all: bool = False
    status: Optional[str] = None
    # Explicit confirmation payload for destructive scope. Required when
    # delete_all=True; the X-Confirm-Delete header is always required.
    confirm: bool = False


_BULK_STATUSES = {"draft", "scheduled", "published", "failed"}

_MAX_BULK_IDS = 500


@router.post("/bulk-delete", response_model=dict)
def bulk_delete_endpoint(
    data: BulkDeleteRequest,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> dict:
    """Delete many posts at once (explicit ids, or all / all-in-status)."""
    if not data.delete_all and not data.ids:
        raise HTTPException(status_code=422, detail="Provide ids or delete_all=true.")
    if data.delete_all and not data.confirm:
        raise HTTPException(
            status_code=422,
            detail="Bulk wipe requires confirm=true in the payload.",
        )
    if data.status is not None and data.status not in _BULK_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status {data.status!r}. Allowed: {', '.join(sorted(_BULK_STATUSES))}.",
        )
    unique_ids = sorted({item for item in (data.ids or []) if isinstance(item, int) and item > 0})
    if data.ids and not unique_ids:
        raise HTTPException(status_code=422, detail="Provide at least one positive post id.")
    if len(unique_ids) > _MAX_BULK_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Too many ids (max {_MAX_BULK_IDS}).",
        )
    # Snapshot before deletion so the bulk entry stays restorable. One query for
    # the id branch (no per-id get_post round-trips / N+1).
    from app.models.post import Post as _Post

    if data.delete_all:
        query = db.query(_Post)
        if data.status:
            query = query.filter(_Post.status == data.status)
        targets = query.all()
    elif unique_ids:
        targets = db.query(_Post).filter(_Post.id.in_(unique_ids)).all()
    else:
        targets = []
    snapshot = {"posts": [log_service.post_to_dict(post) for post in targets]}
    deleted = post_service.bulk_delete_posts(db, ids=unique_ids, delete_all=data.delete_all, status=data.status)
    log_service.add_log(
        db,
        "posts_bulk_deleted",
        f"{deleted} post(s) deleted in bulk.",
        snapshot=snapshot,
        entity_type="posts",
    )
    return {"deleted": deleted}


@router.get("", response_model=Page[PostRead])
def list_posts_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> dict:
    """List posts with pagination and optional filters."""
    items = post_service.list_posts(
        db, skip=skip, limit=limit, status=status, product_id=product_id
    )
    total = post_service.count_posts(db, status=status, product_id=product_id)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("", response_model=PostRead, status_code=201)
def create_post_endpoint(
    data: PostCreate, db: Session = Depends(get_db)
) -> Post:
    """Create a manual draft post and log the event."""
    if data.product_id is not None and product_service.get_product(
        db, data.product_id
    ) is None:
        raise HTTPException(
            status_code=404, detail=f"Product {data.product_id} not found."
        )
    post = post_service.create_post(db, data)
    log_service.add_log(
        db, "post_created", f"Post {post.id} created.", post_id=post.id
    )
    return post


@router.get("/{post_id}", response_model=PostRead)
def get_post_endpoint(post_id: int, db: Session = Depends(get_db)) -> Post:
    """Return a single post by id."""
    post = post_service.get_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return post


@router.patch("/{post_id}", response_model=PostRead)
def update_post_endpoint(
    post_id: int, data: PostUpdate, db: Session = Depends(get_db)
) -> Post:
    """Partially update a post and log the event."""
    try:
        post = post_service.update_post(db, post_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    log_service.add_log(
        db, "post_updated", f"Post {post.id} updated.", post_id=post.id
    )
    return post


@router.delete("/{post_id}", status_code=204)
def delete_post_endpoint(
    post_id: int,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> Response:
    """Delete a post and log the event with a restorable snapshot."""
    post = post_service.get_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    snapshot = {"post": log_service.post_to_dict(post)}
    post_service.delete_post(db, post_id)
    log_service.add_log(
        db,
        "post_deleted",
        f"Post {post_id} deleted.",
        post_id=None,
        snapshot=snapshot,
        entity_type="post",
        entity_id=post_id,
    )
    return Response(status_code=204)


@router.post("/{post_id}/schedule", response_model=PostRead)
def schedule_post_endpoint(
    post_id: int, body: SchedulePostRequest, db: Session = Depends(get_db)
) -> Post:
    """Schedule a draft or failed post for a future time."""
    scheduled_at = body.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    try:
        post = post_service.schedule_post(db, post_id, scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    log_service.add_log(
        db,
        "post_scheduled",
        f"Post {post.id} scheduled for {post.scheduled_at}.",
        post_id=post.id,
    )
    return post


@router.post("/{post_id}/unschedule", response_model=PostRead)
def unschedule_post_endpoint(
    post_id: int, db: Session = Depends(get_db)
) -> Post:
    """Return a scheduled post to draft status."""
    try:
        post = post_service.unschedule_post(db, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    log_service.add_log(
        db, "post_unscheduled", f"Post {post.id} unscheduled.", post_id=post.id
    )
    return post


@router.post("/{post_id}/duplicate", response_model=PostRead, status_code=201)
def duplicate_post_endpoint(
    post_id: int, db: Session = Depends(get_db)
) -> Post:
    """Create a draft copy of a post and log the event."""
    post = post_service.duplicate_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    log_service.add_log(
        db,
        "post_duplicated",
        f"Post {post.id} duplicated from post {post_id}.",
        post_id=post.id,
    )
    return post


@router.post("/{post_id}/publish", response_model=PostRead)
async def publish_post_endpoint(
    post_id: int, db: Session = Depends(get_db)
) -> Post:
    """Publish a draft, scheduled or failed post to the Facebook Page."""
    if post_service.get_post(db, post_id) is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    try:
        return await publish_post(db, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FacebookConfigError as exc:
        raise HTTPException(status_code=503, detail=redact_token_text(str(exc)))
    except FacebookAuthError:
        raise HTTPException(
            status_code=401, detail="Facebook token invalid or expired"
        )
    except FacebookRateLimitError as exc:
        raise HTTPException(status_code=429, detail=redact_token_text(str(exc)))
    except FacebookError as exc:
        raise HTTPException(status_code=502, detail=redact_token_text(str(exc)))
