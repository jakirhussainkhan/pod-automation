"""Pydantic schemas for products."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ProductStatus


class ProductBase(BaseModel):
    """Shared product fields."""

    title: str = Field(min_length=1, max_length=200)
    niche: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    design_url: Optional[str] = Field(default=None, max_length=500)
    mockup_url: Optional[str] = Field(default=None, max_length=500)
    store_url: Optional[str] = Field(default=None, max_length=500)
    price: Optional[Decimal] = None
    tags: list[str] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.active

    @field_validator("title", "niche")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Ensure title and niche are not blank after stripping."""
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("price")
    @classmethod
    def _price_non_negative(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure price is >= 0 when provided."""
        if value is not None and value < 0:
            raise ValueError("price must be >= 0")
        return value


class ProductCreate(ProductBase):
    """Schema for creating a product."""


class ProductUpdate(BaseModel):
    """Schema for updating a product; all fields optional."""

    title: Optional[str] = Field(default=None, max_length=200)
    niche: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    design_url: Optional[str] = Field(default=None, max_length=500)
    mockup_url: Optional[str] = Field(default=None, max_length=500)
    store_url: Optional[str] = Field(default=None, max_length=500)
    price: Optional[Decimal] = None
    tags: Optional[list[str]] = None
    status: Optional[ProductStatus] = None

    @field_validator("title", "niche")
    @classmethod
    def _not_blank_if_provided(cls, value: Optional[str]) -> Optional[str]:
        """Ensure provided title/niche are not blank."""
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("price")
    @classmethod
    def _price_non_negative(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure price is >= 0 when provided."""
        if value is not None and value < 0:
            raise ValueError("price must be >= 0")
        return value


class ProductRead(ProductBase):
    """Schema for reading a product."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime
