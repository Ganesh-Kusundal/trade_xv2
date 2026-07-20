"""Orchestrator models — domain DTOs only (REF-16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from domain.models.features import FeatureSet
from domain.models.trading import SignalDTO
from domain.ports.time_service import get_current_clock


def _utc_now() -> datetime:
    return get_current_clock().now()


@dataclass(frozen=True)
class ExecutionRequest:
    signal: SignalDTO
    correlation_id: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass
class ExecutionResult:
    success: bool
    order_id: str | None = None
    error: str | None = None
    signal: SignalDTO | None = None


@runtime_checkable
class FeatureFetcher(Protocol):
    def fetch(self, symbol: str) -> FeatureSet | None: ...


__all__ = ["ExecutionRequest", "ExecutionResult", "FeatureFetcher"]
