"""Observability ports for event bus and OMS integration."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventMetricsPort(Protocol):
    """Counter store for event bus publish/dispatch/failure outcomes."""

    def inc(self, event_type: str, outcome: str, by: int = 1) -> None: ...

    def snapshot(self) -> dict[tuple[str, str], int]: ...


@runtime_checkable
class AlertingEnginePort(Protocol):
    """Threshold-based alerting evaluated against event metrics."""

    def evaluate(self) -> list[Any]: ...

    def stop(self) -> None: ...


@runtime_checkable
class TracerPort(Protocol):
    """Protocol for function-level tracing with correlation IDs."""

    def trace_operation(self, operation_name: str) -> Any: ...
