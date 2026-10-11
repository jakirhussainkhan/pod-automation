"""Product ORM model."""

from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    """Print-on-demand product that posts can be generated for."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    niche: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    design_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mockup_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    store_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # Demo-data flag: seed rows are True; user-created rows stay False so
    # "Clear Demo Data" can purge only seeded content.
    is_demo: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0", index=True
    )

    posts: Mapped[list["Post"]] = relationship(
        "Post",
        back_populates="product",
        cascade="all, delete-orphan",
    )
