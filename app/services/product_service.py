"""CRUD service for products."""

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import ProductStatus
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate


def create_product(db: Session, data: ProductCreate) -> Product:
    """Create a product and commit it."""
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def get_product(db: Session, product_id: int) -> Optional[Product]:
    """Return a product by id, or None when not found."""
    return db.get(Product, product_id)


def list_products(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    niche: Optional[str] = None,
    status: Optional[str | ProductStatus] = None,
    search: Optional[str] = None,
) -> list[Product]:
    """List products with optional niche, status and text search filters."""
    query = db.query(Product)
    if niche:
        query = query.filter(Product.niche == niche)
    if status:
        status_value = status.value if isinstance(status, ProductStatus) else status
        query = query.filter(Product.status == status_value)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(Product.title.ilike(like), Product.description.ilike(like))
        )
    return query.order_by(Product.id.desc()).offset(skip).limit(limit).all()


def update_product(
    db: Session, product_id: int, data: ProductUpdate
) -> Optional[Product]:
    """Update a product; return None when not found."""
    product = db.get(Product, product_id)
    if product is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int) -> bool:
    """Delete a product; return False when not found."""
    product = db.get(Product, product_id)
    if product is None:
        return False
    db.delete(product)
    db.commit()
    return True


def count_products(
    db: Session,
    niche: Optional[str] = None,
    status: Optional[str | ProductStatus] = None,
    search: Optional[str] = None,
) -> int:
    """Return the number of products matching optional filters."""
    query = db.query(func.count(Product.id))
    if niche:
        query = query.filter(Product.niche == niche)
    if status:
        status_value = status.value if isinstance(status, ProductStatus) else status
        query = query.filter(Product.status == status_value)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(Product.title.ilike(like), Product.description.ilike(like))
        )
    return query.scalar() or 0


def list_niches(db: Session) -> list[str]:
    """Return distinct product niches, sorted alphabetically."""
    rows = db.query(Product.niche).distinct().order_by(Product.niche.asc()).all()
    return [row[0] for row in rows if row[0]]
