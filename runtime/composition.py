"""Neutral composition helpers for runtime/API bootstrap."""

from __future__ import annotations

from typing import Any


def create_api_event_bus(*, maxsize: int = 2000) -> tuple[Any, Any]:
    """Create the shared AsyncEventBus used by API bootstrap."""
    from infrastructure.event_bus.factory import AsyncEventBusFactory

    return AsyncEventBusFactory.create_from_config(
        force_async=True,
        maxsize=maxsize,
    )
