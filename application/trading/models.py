"""Orchestrator models — domain DTOs only (REF-16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from domain.models.features import FeatureSet
from domain.models.trading import SignalDTO


@dataclass(frozen=True)
class ExecutionRequest:
    signal: SignalDTO
    correlation_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
