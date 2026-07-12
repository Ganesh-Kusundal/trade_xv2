"""Neutral composition helpers for runtime/API bootstrap."""

from __future__ import annotations

from typing import Any


def create_api_event_bus(*, maxsize: int = 2000) -> tuple[Any, Any]:
    """Create the shared EventBus used by API bootstrap (metrics + DLQ)."""
    from infrastructure.bootstrap import build_production_event_bus
    from runtime.resilience import ResilienceConfig

    bus = build_production_event_bus(resilience=ResilienceConfig.from_env())
    config = {
        "maxsize": maxsize,
        "created_by": "create_api_event_bus",
        "bus_type": "synchronous",
    }
    return bus, config
