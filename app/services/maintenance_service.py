"""Maintenance service: demo-only cleanup + guarded full wipe."""

from sqlalchemy.orm import Session

from app.models.group_lead import GroupLead
from app.models.group_post_queue import GroupPostQueue
from app.models.post import Post
from app.models.product import Product
from app.services import log_service, settings_service

_SEED_FLAG = "demo_seed_done"


def _demo_only_query(model, db: Session):
    """Return a query limited to seeded demo rows (is_demo=True)."""
    if hasattr(model, "is_demo"):
        return db.query(model).filter(model.is_demo.is_(True))
    return db.query(model).filter(False)


def clear_dummy_data(db: Session, wipe_all: bool = False) -> dict:
    """Purge demo rows, or wipe everything when ``wipe_all`` is True.

    Safe default (``wipe_all=False``) deletes strictly rows where
    ``is_demo == True``, leaving real leads, posts, and revenue records
    intact. Real posts/leads linked to demo products are detached
    (``product_id=None``) instead of cascade-deleted.

    Full wipe (``wipe_all=True``, caller must have validated the
    ``"WIPE ALL DATA"`` confirmation text plus the destructive header)
    removes every product, post, lead, and queued post.

    The seed-once flag is set so demo data is never resurrected on
    restart. App settings and activity logs are preserved. A JSON snapshot
    of every wiped row is stored on the ``dummy_data_cleared`` entry so
    the operation can be undone via ``POST /api/logs/restore``.
    """
    try:
        if wipe_all:
            product_rows = db.query(Product).all()
            post_rows = db.query(Post).all()
            lead_rows = db.query(GroupLead).all()
            queued_rows = db.query(GroupPostQueue).all()
        else:
            product_rows = _demo_only_query(Product, db).all()
            post_rows = _demo_only_query(Post, db).all()
            lead_rows = _demo_only_query(GroupLead, db).all()
            queued_rows = _demo_only_query(GroupPostQueue, db).all()
        snapshot = {
            "products": [log_service.product_to_dict(item) for item in product_rows],
            "posts": [log_service.post_to_dict(item) for item in post_rows],
            "group_leads": [log_service.lead_to_dict(item) for item in lead_rows],
            "group_post_queue": [log_service.queue_to_dict(item) for item in queued_rows],
        }
        counts = {
            "products": len(product_rows),
            "posts": len(post_rows),
            "leads": len(lead_rows),
            "queued_posts": len(queued_rows),
        }
        if wipe_all:
            # Batch deletes avoid N+1 ORM loads on large DBs.
            db.query(GroupPostQueue).delete(synchronize_session=False)
            db.query(GroupLead).delete(synchronize_session=False)
            db.query(Post).delete(synchronize_session=False)
            db.query(Product).delete(synchronize_session=False)
        else:
            demo_product_ids = [item.id for item in product_rows if item.id is not None]
            if demo_product_ids:
                # Detach real content linked to demo products so the
                # cascade never eats user data or revenue records.
                db.query(Post).filter(
                    Post.is_demo.is_(False),
                    Post.product_id.in_(demo_product_ids),
                ).update(
                    {Post.product_id: None}, synchronize_session=False
                )
                db.query(GroupLead).filter(
                    GroupLead.is_demo.is_(False),
                    GroupLead.product_id.in_(demo_product_ids),
                ).update(
                    {GroupLead.product_id: None}, synchronize_session=False
                )
            db.query(GroupPostQueue).filter(
                GroupPostQueue.is_demo.is_(True)
            ).delete(synchronize_session=False)
            db.query(GroupLead).filter(
                GroupLead.is_demo.is_(True)
            ).delete(synchronize_session=False)
            db.query(Post).filter(
                Post.is_demo.is_(True)
            ).delete(synchronize_session=False)
            db.query(Product).filter(
                Product.is_demo.is_(True)
            ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    settings_service.set_setting(db, _SEED_FLAG, "true")
    result = dict(counts)
    mode = "wiped ALL data" if wipe_all else "cleared demo data"
    log_service.add_log(
        db,
        "dummy_data_cleared",
        f"{mode}: {counts['products']} products, {counts['posts']} posts, "
        f"{counts['leads']} leads, {counts['queued_posts']} queued posts.",
        snapshot=snapshot,
        entity_type="dummy_data",
    )
    return result
