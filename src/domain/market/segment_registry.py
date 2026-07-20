"""Broker segment mapper registry — domain-owned lookup, broker-owned registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.market.segment_mapper import SegmentMapper

_MAPPER_FACTORIES: dict[str, Callable[[], SegmentMapper]] = {}


def register_segment_mapper(
    broker_id: str,
    factory: Callable[[], SegmentMapper],
) -> None:
    """Register a segment mapper factory for a broker plugin."""
    key = (broker_id or "").lower().strip()
    if not key:
        raise ValueError("broker_id is required for segment mapper registration")
    _MAPPER_FACTORIES[key] = factory


def segment_mapper_for(broker_id: str) -> SegmentMapper:
    """Return the registered segment mapper for a broker."""
    key = (broker_id or "dhan").lower().strip()
    factory = _MAPPER_FACTORIES.get(key)
    if factory is None:
        raise LookupError(
            f"No SegmentMapper registered for broker {key!r}. "
            "Ensure the broker plugin package is imported (tradex.brokers entry point)."
        )
    return factory()


def registered_broker_ids() -> frozenset[str]:
    """Broker IDs with a registered segment mapper (tests/diagnostics)."""
    return frozenset(_MAPPER_FACTORIES.keys())
