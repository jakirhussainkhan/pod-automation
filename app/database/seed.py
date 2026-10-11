"""Demo data seeding for development."""

import logging
from decimal import Decimal

from app.database.init_db import init_db
from app.database.session import SessionLocal
from app.models.app_setting import AppSetting
from app.models.post import Post
from app.models.product import Product

logger = logging.getLogger("pod-automation")

_SEED_FLAG = "demo_seed_done"


DEMO_PRODUCTS_WITH_POSTS: list[dict] = [
    {
        "product": {
            "title": "Funny Cat Astronaut T-Shirt",
            "niche": "funny-cats",
            "description": "A hilarious cat astronaut floating in space with pizza slices as stars. Perfect for cat lovers and space fans.",
            "design_url": "https://example.com/designs/cat-astronaut.png",
            "mockup_url": "https://example.com/mockups/cat-astronaut-tshirt.png",
            "store_url": "https://example.com/store/cat-astronaut-tee",
            "price": Decimal("24.99"),
            "tags": ["cats", "funny", "space", "tshirt"],
            "status": "active",
        },
        "post": {
            "caption": "New drop! Our Funny Cat Astronaut Tee just landed. Tag a cat lover who needs this!",
            "hashtags": ["#CatLovers", "#FunnyTee", "#POD"],
        },
    },
    {
        "product": {
            "title": "Motivational Mountain Hiker Hoodie",
            "niche": "outdoors",
            "description": "Inspirational mountain landscape with 'Conquer Every Peak' typography. Cozy hoodie for hikers and adventurers.",
            "design_url": "https://example.com/designs/mountain-hiker.png",
            "mockup_url": "https://example.com/mockups/mountain-hiker-hoodie.png",
            "store_url": "https://example.com/store/mountain-hiker-hoodie",
            "price": Decimal("44.99"),
            "tags": ["hiking", "mountains", "motivation", "hoodie"],
            "status": "active",
        },
        "post": {
            "caption": "Conquer every peak with our Motivational Mountain Hiker Hoodie. Built for the trail, styled for the street.",
            "hashtags": ["#Hiking", "#Outdoors", "#HoodieSeason"],
        },
    },
    {
        "product": {
            "title": "Vintage Retro Gamer Mug",
            "niche": "gaming",
            "description": "Retro pixel-art game controller design with neon arcade vibes. 11oz ceramic mug for gamers.",
            "design_url": "https://example.com/designs/retro-gamer.png",
            "mockup_url": "https://example.com/mockups/retro-gamer-mug.png",
            "store_url": "https://example.com/store/retro-gamer-mug",
            "price": Decimal("16.99"),
            "tags": ["gaming", "retro", "mug", "pixel-art"],
            "status": "active",
        },
        "post": {
            "caption": "Level up your mornings with the Vintage Retro Gamer Mug. Pixel-perfect coffee time!",
            "hashtags": ["#Gaming", "#RetroGaming", "#MugLovers"],
        },
    },
]


def _mark_seed_done(db) -> None:
    """Persist the seed-once flag so wiped data is never resurrected."""
    row = db.query(AppSetting).filter(AppSetting.key == _SEED_FLAG).first()
    if row is None:
        db.add(AppSetting(key=_SEED_FLAG, value="true"))
    else:
        row.value = "true"
    db.commit()


def backfill_demo_flags() -> None:
    """Tag pre-hardening demo rows (created before is_demo) idempotently."""
    db = SessionLocal()
    try:
        demo_titles = {item["product"]["title"] for item in DEMO_PRODUCTS_WITH_POSTS}
        demo_captions = {item["post"]["caption"] for item in DEMO_PRODUCTS_WITH_POSTS}
        updated = 0
        if demo_titles:
            updated += (
                db.query(Product)
                .filter(Product.title.in_(demo_titles), Product.is_demo.is_(False))
                .update({Product.is_demo: True}, synchronize_session=False)
            )
        if demo_captions:
            updated += (
                db.query(Post)
                .filter(Post.caption.in_(demo_captions), Post.is_demo.is_(False))
                .update({Post.is_demo: True}, synchronize_session=False)
            )
        if updated:
            db.commit()
            logger.info("Backfilled is_demo=True on %d legacy demo rows.", updated)
        else:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception("Demo flag backfill failed.")
    finally:
        db.close()


def seed_demo_data() -> None:
    """Insert demo products and draft posts exactly once per database."""
    db = SessionLocal()
    try:
        flag = db.query(AppSetting).filter(AppSetting.key == _SEED_FLAG).first()
        if flag is not None and (flag.value or "").lower() == "true":
            logger.info("Demo seed already completed, skipping seed.")
            db.close()
            backfill_demo_flags()
            return
        existing = db.query(Product).count()
        if existing > 0:
            logger.info("Demo data already present (%d products), skipping seed.", existing)
            _mark_seed_done(db)
            return

        products_data = [item["product"] for item in DEMO_PRODUCTS_WITH_POSTS]
        captions_data = [
            (item["post"]["caption"], item["post"]["hashtags"])
            for item in DEMO_PRODUCTS_WITH_POSTS
        ]

        products: list[Product] = []
        for item in products_data:
            product = Product(**{**item, "is_demo": True})
            db.add(product)
            products.append(product)
        db.flush()

        for product, (caption, hashtags) in zip(products, captions_data):
            post = Post(
                product_id=product.id,
                caption=caption,
                hashtags=hashtags,
                image_url=product.mockup_url,
                status="draft",
                is_demo=True,
            )
            db.add(post)

        db.commit()
        logger.info("Seeded 3 demo products and 3 draft posts.")
        _mark_seed_done(db)
    finally:
        db.close()


if __name__ == "__main__":
    """Initialize tables then seed demo data."""
    init_db()
    seed_demo_data()
