"""Service for activity log entries, including soft-delete snapshots + restore."""

import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.activity_log import RESTORABLE_LOG_EVENTS, ActivityLog

logger = logging.getLogger("pod-automation")

__all__ = [
    "RESTORABLE_LOG_EVENTS",
    "add_log",
    "list_logs",
    "count_logs",
    "clear_logs",
    "is_restorable",
    "restore_logs",
    "product_to_dict",
    "post_to_dict",
]


def _dump_snapshot(snapshot: Optional[dict[str, Any]]) -> Optional[str]:
    """Serialize a snapshot dict to JSON, returning None when empty."""
    if not snapshot:
        return None
    try:
        return json.dumps(snapshot, default=str)
    except (TypeError, ValueError):
        logger.exception("Failed to serialize activity log snapshot.")
        return None


def _load_snapshot(entry: ActivityLog) -> Optional[dict[str, Any]]:
    """Parse an entry snapshot back into a dict, or None when unusable."""
    if not entry.snapshot:
        return None
    try:
        data = json.loads(entry.snapshot)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def add_log(
    db: Session,
    event_type: str,
    message: str,
    level: str = "INFO",
    post_id: Optional[int] = None,
    snapshot: Optional[dict[str, Any]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> ActivityLog:
    """Create an activity log entry and commit it.

    Deletion callers pass a JSON-serializable ``snapshot`` of the removed
    rows so the entry can later be restored via ``restore_logs``.
    """
    entry = ActivityLog(
        event_type=event_type,
        message=message,
        level=level,
        post_id=post_id,
        snapshot=_dump_snapshot(snapshot),
        entity_type=entity_type,
        entity_id=entity_id,
        restored=False,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_logs(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    level: Optional[str] = None,
) -> list[ActivityLog]:
    """List log entries, optionally filtered by level."""
    query = db.query(ActivityLog)
    if level:
        query = query.filter(ActivityLog.level == level)
    return query.order_by(ActivityLog.id.desc()).offset(skip).limit(limit).all()


def count_logs(db: Session, level: Optional[str] = None) -> int:
    """Count log entries with an optional level filter."""
    query = db.query(func.count(ActivityLog.id))
    if level:
        query = query.filter(ActivityLog.level == level)
    return query.scalar() or 0


def clear_logs(db: Session) -> int:
    """Delete all activity log entries and return the removed count."""
    deleted = db.query(ActivityLog).delete(synchronize_session=False)
    db.commit()
    return deleted or 0


def prune_old_logs(db: Session, retention_days: int) -> int:
    """Delete unrestorable logs older than the retention window.

    Entries flagged ``restored`` (recoverable snapshots) are never
    pruned so restores keep working.
    """
    from datetime import datetime, timedelta, timezone

    window = max(1, min(365, int(retention_days)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)
    try:
        deleted = (
            db.query(ActivityLog)
            .filter(ActivityLog.created_at < cutoff)
            .filter(ActivityLog.restored.is_(False))
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted or 0)
    except Exception:
        db.rollback()
        logger.exception("Log pruning failed.")
        raise


def is_restorable(entry: ActivityLog) -> bool:
    """Return True when an entry is a restorable deletion with a snapshot."""
    return entry.event_type in RESTORABLE_LOG_EVENTS and bool(entry.snapshot)


# -- Snapshot serializers ----------------------------------------------------


def product_to_dict(product: Any) -> dict[str, Any]:
    """Serialize a Product ORM row to a JSON-safe dict."""
    price = getattr(product, "price", None)
    try:
        price_value: Optional[float] = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_value = None
    return {
        "id": getattr(product, "id", None),
        "title": getattr(product, "title", None),
        "niche": getattr(product, "niche", None),
        "description": getattr(product, "description", None),
        "design_url": getattr(product, "design_url", None),
        "mockup_url": getattr(product, "mockup_url", None),
        "store_url": getattr(product, "store_url", None),
        "price": price_value,
        "tags": list(getattr(product, "tags", None) or []),
        "status": getattr(product, "status", "active") or "active",
        "is_demo": bool(getattr(product, "is_demo", False)),
    }


def post_to_dict(post: Any) -> dict[str, Any]:
    """Serialize a Post ORM row to a JSON-safe dict."""
    scheduled = getattr(post, "scheduled_at", None)
    published = getattr(post, "published_at", None)
    return {
        "id": getattr(post, "id", None),
        "product_id": getattr(post, "product_id", None),
        "caption": getattr(post, "caption", None),
        "hashtags": list(getattr(post, "hashtags", None) or []),
        "image_url": getattr(post, "image_url", None),
        "status": getattr(post, "status", "draft") or "draft",
        "scheduled_at": scheduled.isoformat() if scheduled else None,
        "published_at": published.isoformat() if published else None,
        "facebook_post_id": getattr(post, "facebook_post_id", None),
        "error_message": getattr(post, "error_message", None),
        "ai_provider": getattr(post, "ai_provider", None),
        "ai_model": getattr(post, "ai_model", None),
        "is_demo": bool(getattr(post, "is_demo", False)),
    }


def lead_to_dict(lead: Any) -> dict[str, Any]:
    """Serialize a GroupLead ORM row to a JSON-safe dict."""
    step1 = getattr(lead, "step1_sent_at", None)
    step2 = getattr(lead, "step2_sent_at", None)
    checked = getattr(lead, "last_checked_at", None)
    due = getattr(lead, "follow_up_due_at", None)
    fsent = getattr(lead, "follow_up_sent_at", None)
    return {
        "id": getattr(lead, "id", None),
        "username": getattr(lead, "username", None),
        "comment_text": getattr(lead, "comment_text", None),
        "group_name": getattr(lead, "group_name", None),
        "intent": getattr(lead, "intent", "low") or "low",
        "product_id": getattr(lead, "product_id", None),
        "message1": getattr(lead, "message1", "") or "",
        "message2": getattr(lead, "message2", "") or "",
        "status": getattr(lead, "status", "unsent") or "unsent",
        "user_profile_link": getattr(lead, "user_profile_link", None),
        "conversion_value": float(getattr(lead, "conversion_value", 0.0) or 0.0),
        "is_demo": bool(getattr(lead, "is_demo", False)),
        "step1_sent_at": step1.isoformat() if hasattr(step1, "isoformat") else None,
        "step2_sent_at": step2.isoformat() if hasattr(step2, "isoformat") else None,
        "assigned_account_id": getattr(lead, "assigned_account_id", None),
        "last_checked_at": checked.isoformat() if hasattr(checked, "isoformat") else None,
        "follow_up_due_at": due.isoformat() if hasattr(due, "isoformat") else None,
        "follow_up_sent_at": fsent.isoformat() if hasattr(fsent, "isoformat") else None,
        "follow_up_count": int(getattr(lead, "follow_up_count", 0) or 0),
        "reply_state": getattr(lead, "reply_state", "unknown") or "unknown",
        "source_template": getattr(lead, "source_template", None),
    }


def queue_to_dict(item: Any) -> dict[str, Any]:
    """Serialize a GroupPostQueue ORM row to a JSON-safe dict."""
    copied = getattr(item, "copied_at", None)
    posted = getattr(item, "posted_at", None)
    return {
        "id": getattr(item, "id", None),
        "niche": getattr(item, "niche", "car") or "car",
        "subculture": getattr(item, "subculture", "auto") or "auto",
        "template": getattr(item, "template", "") or "",
        "trigger": getattr(item, "trigger", "auto") or "auto",
        "caption": getattr(item, "caption", "") or "",
        "hashtags": list(getattr(item, "hashtags", None) or []),
        "call_to_action": getattr(item, "call_to_action", "") or "",
        "image_idea": getattr(item, "image_idea", "") or "",
        "status": getattr(item, "status", "queued") or "queued",
        "is_demo": bool(getattr(item, "is_demo", False)),
        "copied_at": copied.isoformat() if hasattr(copied, "isoformat") else None,
        "posted_at": posted.isoformat() if hasattr(posted, "isoformat") else None,
        "template_name": getattr(item, "template_name", None),
    }


def _parse_dt(value: Any) -> Optional[datetime]:
    """Parse an ISO datetime string, returning None when unusable."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


# -- Restore -----------------------------------------------------------------


def _restore_products(
    db: Session, rows: list[dict[str, Any]], id_map: dict[int, int]
) -> int:
    """Re-insert missing products; return the number re-created."""
    from app.models.product import Product

    restored = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        old_id = row.get("id")
        if isinstance(old_id, int) and db.get(Product, old_id) is not None:
            id_map[old_id] = old_id
            continue
        price = row.get("price")
        price_value: Optional[Decimal] = None
        if price is not None:
            try:
                price_value = Decimal(str(price))
            except (InvalidOperation, ValueError, TypeError):
                price_value = None
        product = Product(
            title=row.get("title") or "Restored product",
            niche=row.get("niche") or "restored",
            description=row.get("description"),
            design_url=row.get("design_url"),
            mockup_url=row.get("mockup_url"),
            store_url=row.get("store_url"),
            price=price_value,
            tags=list(row.get("tags") or []),
            status=row.get("status") or "active",
            is_demo=bool(row.get("is_demo", False)),
        )
        # Preserve the original id when the slot is free, so linked posts
        # keep working; otherwise let SQLite assign a fresh id.
        if isinstance(old_id, int) and db.get(Product, old_id) is None:
            product.id = old_id
        db.add(product)
        db.flush()
        if isinstance(old_id, int):
            id_map[old_id] = product.id
        restored += 1
    return restored


def _restore_posts(
    db: Session,
    rows: list[dict[str, Any]],
    product_id_map: Optional[dict[int, int]] = None,
) -> int:
    """Re-insert missing posts; return the number re-created."""
    from app.models.post import Post
    from app.models.product import Product

    restored = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        old_id = row.get("id")
        if isinstance(old_id, int) and db.get(Post, old_id) is not None:
            continue
        product_id = row.get("product_id")
        if product_id_map and isinstance(product_id, int):
            product_id = product_id_map.get(product_id, product_id)
        if product_id is not None and db.get(Product, product_id) is None:
            # Linked product is gone and not part of this restore batch:
            # keep the post as a standalone draft instead of failing the FK.
            product_id = None
        post = Post(
            product_id=product_id,
            caption=row.get("caption") or "Restored post",
            hashtags=list(row.get("hashtags") or []),
            image_url=row.get("image_url"),
            status=row.get("status") or "draft",
            scheduled_at=_parse_dt(row.get("scheduled_at")),
            published_at=_parse_dt(row.get("published_at")),
            facebook_post_id=row.get("facebook_post_id"),
            error_message=row.get("error_message"),
            ai_provider=row.get("ai_provider"),
            ai_model=row.get("ai_model"),
            is_demo=bool(row.get("is_demo", False)),
        )
        if isinstance(old_id, int) and db.get(Post, old_id) is None:
            post.id = old_id
        db.add(post)
        db.flush()
        restored += 1
    return restored


def _restore_leads(db: Session, rows: list[dict[str, Any]]) -> int:
    """Re-insert missing group leads; return the number re-created."""
    from app.models.group_lead import GroupLead
    from app.models.product import Product

    restored = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        old_id = row.get("id")
        if isinstance(old_id, int) and db.get(GroupLead, old_id) is not None:
            continue
        product_id = row.get("product_id")
        if product_id is not None and db.get(Product, product_id) is None:
            product_id = None
        lead = GroupLead(
            username=row.get("username") or "group_member",
            comment_text=row.get("comment_text") or "",
            group_name=row.get("group_name"),
            intent=row.get("intent") or "low",
            product_id=product_id,
            message1=row.get("message1") or "",
            message2=row.get("message2") or "",
            status=row.get("status") or "unsent",
            user_profile_link=row.get("user_profile_link"),
            conversion_value=float(row.get("conversion_value") or 0.0),
            is_demo=bool(row.get("is_demo", False)),
            step1_sent_at=_parse_dt(row.get("step1_sent_at")),
            step2_sent_at=_parse_dt(row.get("step2_sent_at")),
            assigned_account_id=row.get("assigned_account_id"),
            last_checked_at=_parse_dt(row.get("last_checked_at")),
            follow_up_due_at=_parse_dt(row.get("follow_up_due_at")),
            follow_up_sent_at=_parse_dt(row.get("follow_up_sent_at")),
            follow_up_count=int(row.get("follow_up_count") or 0),
            reply_state=row.get("reply_state") or "unknown",
            source_template=row.get("source_template"),
        )
        if isinstance(old_id, int) and db.get(GroupLead, old_id) is None:
            lead.id = old_id
        db.add(lead)
        db.flush()
        restored += 1
    return restored


def _restore_queue(db: Session, rows: list[dict[str, Any]]) -> int:
    """Re-insert missing queued group posts; return the number re-created."""
    from app.models.group_post_queue import GroupPostQueue

    restored = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        old_id = row.get("id")
        if isinstance(old_id, int) and db.get(GroupPostQueue, old_id) is not None:
            continue
        item = GroupPostQueue(
            niche=row.get("niche") or "car",
            subculture=row.get("subculture") or "auto",
            template=row.get("template") or "",
            trigger=row.get("trigger") or "auto",
            caption=row.get("caption") or "",
            hashtags=list(row.get("hashtags") or []),
            call_to_action=row.get("call_to_action") or "",
            image_idea=row.get("image_idea") or "",
            status=row.get("status") or "queued",
            is_demo=bool(row.get("is_demo", False)),
            copied_at=_parse_dt(row.get("copied_at")),
            posted_at=_parse_dt(row.get("posted_at")),
            template_name=row.get("template_name") or row.get("template") or None,
        )
        if isinstance(old_id, int) and db.get(GroupPostQueue, old_id) is None:
            item.id = old_id
        db.add(item)
        db.flush()
        restored += 1
    return restored


def restore_logs(db: Session, log_ids: list[int]) -> dict[str, Any]:
    """Restore soft-deleted rows captured in the given log entries.

    Each eligible entry is restored at most once: entries without a
    snapshot, of a non-deletion type, or already marked restored are
    reported as skipped. Successfully restored entries are flagged so a
    second restore call is a no-op for them.
    """
    unique_ids = sorted({item for item in (log_ids or []) if isinstance(item, int) and item > 0})
    details: list[dict[str, Any]] = []
    totals = {"products": 0, "posts": 0, "leads": 0, "queued_posts": 0}
    restored_logs = 0
    skipped = 0

    for log_id in unique_ids:
        entry = db.get(ActivityLog, log_id)
        if entry is None:
            skipped += 1
            details.append({"log_id": log_id, "status": "skipped", "reason": "log entry not found"})
            continue
        if entry.event_type not in RESTORABLE_LOG_EVENTS:
            skipped += 1
            details.append({"log_id": log_id, "status": "skipped", "reason": f"event {entry.event_type!r} is not restorable"})
            continue
        if entry.restored:
            skipped += 1
            details.append({"log_id": log_id, "status": "skipped", "reason": "already restored"})
            continue
        snapshot = _load_snapshot(entry)
        if not snapshot:
            skipped += 1
            details.append({"log_id": log_id, "status": "skipped", "reason": "no recoverable snapshot on this entry"})
            continue
        try:
            counts = {"products": 0, "posts": 0, "leads": 0, "queued_posts": 0}
            product_id_map: dict[int, int] = {}
            event = entry.event_type
            if event == "product_deleted":
                product = snapshot.get("product")
                posts = snapshot.get("posts") or []
                if isinstance(product, dict):
                    counts["products"] = _restore_products(db, [product], product_id_map)
                if isinstance(posts, list):
                    counts["posts"] = _restore_posts(db, posts, product_id_map)
            elif event == "post_deleted":
                post = snapshot.get("post")
                if isinstance(post, dict):
                    counts["posts"] = _restore_posts(db, [post])
            elif event == "posts_bulk_deleted":
                posts = snapshot.get("posts") or []
                if isinstance(posts, list):
                    counts["posts"] = _restore_posts(db, posts)
            elif event == "dummy_data_cleared":
                products = snapshot.get("products") or []
                posts = snapshot.get("posts") or []
                leads = snapshot.get("group_leads") or snapshot.get("leads") or []
                queued = snapshot.get("group_post_queue") or snapshot.get("queued_posts") or []
                if isinstance(products, list):
                    counts["products"] = _restore_products(db, products, product_id_map)
                if isinstance(posts, list):
                    counts["posts"] = _restore_posts(db, posts, product_id_map)
                if isinstance(leads, list):
                    counts["leads"] = _restore_leads(db, leads)
                if isinstance(queued, list):
                    counts["queued_posts"] = _restore_queue(db, queued)
            else:  # pragma: no cover - guarded by the allowlist above.
                skipped += 1
                details.append({"log_id": log_id, "status": "skipped", "reason": f"event {event!r} is not restorable"})
                continue
            for key in totals:
                totals[key] += counts[key]
            entry.restored = True
            db.commit()
            restored_logs += 1
            details.append({"log_id": log_id, "status": "restored", **counts})
        except Exception as exc:
            db.rollback()
            logger.exception("Restore failed for activity log %s.", log_id)
            skipped += 1
            details.append({"log_id": log_id, "status": "skipped", "reason": f"restore failed: {exc}"})

    if restored_logs:
        try:
            summary = (
                f"Restored {restored_logs} deletion(s): "
                f"{totals['products']} products, {totals['posts']} posts, "
                f"{totals['leads']} leads, {totals['queued_posts']} queued posts."
            )
            add_log(db, "items_restored", summary)
        except Exception:
            logger.exception("Failed to log restore summary.")

    return {
        "restored_logs": restored_logs,
        "skipped": skipped,
        "restored_products": totals["products"],
        "restored_posts": totals["posts"],
        "restored_leads": totals["leads"],
        "restored_queued_posts": totals["queued_posts"],
        "details": details,
    }
