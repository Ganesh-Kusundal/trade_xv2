"""Health & Status schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)
    services: dict[str, str] | None = None


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    ready: bool
    checks: dict[str, bool]
    timestamp: datetime = Field(default_factory=datetime.now)
