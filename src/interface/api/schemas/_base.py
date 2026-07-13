"""Generic API response wrappers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    success: bool = True
    data: T | None = None
    message: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response for list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size > 0 else 0


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str
    message: str
    trace_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    error: ErrorDetail
    timestamp: datetime = Field(default_factory=datetime.now)
