"""Single-post Facebook publisher with idempotency guards."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.post import Post
from app.services import log_service, post_service
from app.services.facebook.client import FacebookClient
from app.services.facebook.exceptions import FacebookError, redact_token_text

logger = logging.getLogger("pod-automation")

_FACEBOOK_TEXT_LIMIT = 63000
_PUBLISHABLE_STATUSES = ("draft", "scheduled", "failed")


def build_message(post: Post) -> str:
    """Build the Facebook text from caption plus hashtags, capped at 63k chars."""
    caption = (post.caption or "").strip()
    tags = " ".join(post.hashtags or [])
    if tags:
        message = caption + "\n\n" + tags if caption else tags
    else:
        message = caption
    return message[:_FACEBOOK_TEXT_LIMIT]


async def publish_post(db: Session, post_id: int) -> Post:
    """Publish one draft/scheduled/failed post to the Facebook Page."""
    from app.services import settings_service

    if settings_service.is_kill_switch_active(db):
        log_service.add_log(
            db,
            "kill_switch_blocked",
            f"Publish of post {post_id} blocked: emergency stop is active.",
            level="WARNING",
            post_id=post_id,
        )
        raise ValueError("Kill switch active — publishing blocked.")
    post = db.get(Post, post_id)
    if post is None:
        raise ValueError(f"Post {post_id} not found.")
    if post.status not in _PUBLISHABLE_STATUSES:
        raise ValueError("Only draft, scheduled or failed posts can be published.")
    post.publish_attempts = (post.publish_attempts or 0) + 1
    post.last_attempt_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(post)

    settings = get_settings()
    logger.info(
        "Publishing post %s (attempt %s, dry_run=%s).",
        post_id,
        post.publish_attempts,
        settings.FACEBOOK_DRY_RUN,
    )
    client = FacebookClient()
    try:
        message = build_message(post)
        if post.image_url:
            result = await client.publish_photo(post.image_url, message)
        else:
            result = await client.publish_text(message)
        facebook_post_id = result["id"]
    except FacebookError as exc:
        safe_message = redact_token_text(str(exc)) or "Facebook publish failed."
        post_service.mark_post_failed(db, post_id, safe_message)
        log_service.add_log(
            db,
            "post_failed",
            f"Post {post_id} failed to publish: {safe_message}",
            level="ERROR",
            post_id=post_id,
        )
        logger.warning("Publish of post %s failed: %s", post_id, safe_message)
        raise
    finally:
        await client.aclose()

    published = post_service.mark_post_published(db, post_id, facebook_post_id)
    log_service.add_log(
        db,
        "post_published",
        f"Post {post_id} published to Facebook ({facebook_post_id}).",
        post_id=post_id,
    )
    logger.info("Post %s published as %s.", post_id, facebook_post_id)
    return published
