"""Shared generic API response models."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Paginated list response with total count."""

    items: list[T]
    total: int
    skip: int
    limit: int


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class ErrorResponse(BaseModel):
    """Error response shape."""

    detail: str
