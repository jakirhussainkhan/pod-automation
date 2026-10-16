"""Product API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.product import Product
from app.routers.deps import require_destructive_confirmation
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import log_service, product_service

router: APIRouter = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=Page[ProductRead])
def list_products_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    niche: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    """List products with pagination and optional filters."""
    items = product_service.list_products(
        db, skip=skip, limit=limit, niche=niche, status=status, search=search
    )
    total = product_service.count_products(
        db, niche=niche, status=status, search=search
    )
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("", response_model=ProductRead, status_code=201)
def create_product_endpoint(
    data: ProductCreate, db: Session = Depends(get_db)
) -> Product:
    """Create a product and log the event."""
    product = product_service.create_product(db, data)
    log_service.add_log(
        db, "product_created", f"Product {product.id} created: {product.title}."
    )
    return product


@router.get("/niches", response_model=list[str])
def list_niches_endpoint(db: Session = Depends(get_db)) -> list[str]:
    """Return distinct product niches, sorted alphabetically."""
    return product_service.list_niches(db)


@router.get("/{product_id}", response_model=ProductRead)
def get_product_endpoint(
    product_id: int, db: Session = Depends(get_db)
) -> Product:
    """Return a single product by id."""
    product = product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found.")
    return product


@router.patch("/{product_id}", response_model=ProductRead)
def update_product_endpoint(
    product_id: int, data: ProductUpdate, db: Session = Depends(get_db)
) -> Product:
    """Partially update a product and log the event."""
    product = product_service.update_product(db, product_id, data)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found.")
    log_service.add_log(
        db, "product_updated", f"Product {product.id} updated: {product.title}."
    )
    return product


@router.delete("/{product_id}", status_code=204)
def delete_product_endpoint(
    product_id: int,
    db: Session = Depends(get_db),
    _confirmed: None = Depends(require_destructive_confirmation),
) -> Response:
    """Delete a product and log the event with a restorable snapshot."""
    product = product_service.get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found.")
    title = product.title
    # Capture the product + its linked posts BEFORE the cascading delete so
    # the `product_deleted` log entry can restore them via /api/logs/restore.
    snapshot = {
        "product": log_service.product_to_dict(product),
        "posts": [log_service.post_to_dict(post) for post in list(product.posts)],
    }
    product_service.delete_product(db, product_id)
    log_service.add_log(
        db,
        "product_deleted",
        f"Product {product_id} deleted: {title}.",
        snapshot=snapshot,
        entity_type="product",
        entity_id=product_id,
    )
    return Response(status_code=204)


@router.post("/restore-seed", response_model=dict)
def restore_seed_endpoint(db: Session = Depends(get_db)) -> dict:
    """Re-insert missing demo seed products/posts (recoverable clean-start).

    Only the 3 known demo products (matched by title) are restored, so user
    data is never duplicated. Useful when the seed snapshot log was cleared.
    """
    from app.database.seed import DEMO_PRODUCTS_WITH_POSTS

    existing_titles = {
        row[0] for row in db.query(Product.title).all() if row[0]
    }
    created_products = 0
    created_posts = 0
    for item in DEMO_PRODUCTS_WITH_POSTS:
        spec = item["product"]
        if spec["title"] in existing_titles:
            continue
        product = Product(**{**spec, "is_demo": True})
        db.add(product)
        db.flush()
        existing_titles.add(spec["title"])
        created_products += 1
        post_spec = item.get("post")
        if post_spec:
            from app.models.post import Post

            db.add(
                Post(
                    product_id=product.id,
                    caption=post_spec["caption"],
                    hashtags=list(post_spec.get("hashtags") or []),
                    image_url=product.mockup_url,
                    status="draft",
                    is_demo=True,
                )
            )
            created_posts += 1
    if created_products or created_posts:
        db.commit()
        log_service.add_log(
            db,
            "seed_restored",
            f"Restored demo seed: {created_products} products, {created_posts} posts.",
            entity_type="seed",
        )
    return {"restored_products": created_products, "restored_posts": created_posts}
