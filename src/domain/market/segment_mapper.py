"""Segment mapping protocol — broker adapters implement wire/domain conversion."""

from __future__ import annotations

from typing import Protocol

from domain.types import ExchangeSegment


class SegmentMapper(Protocol):
    """Bidirectional exchange segment mapping for a broker."""

    broker_id: str

    def to_wire(self, segment: ExchangeSegment) -> str: ...

    def from_wire(self, wire: str) -> ExchangeSegment: ...

    def from_exchange(self, exchange: str) -> ExchangeSegment: ...


def segment_mapper_for(broker_id: str) -> SegmentMapper:
    """Return the segment mapper for a broker (via plugin registry)."""
    from domain.market.segment_registry import segment_mapper_for as _lookup

    return _lookup(broker_id)