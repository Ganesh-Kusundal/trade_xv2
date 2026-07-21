"""SegmentMapperRegistry — plugin registration and fail-closed lookup."""

from __future__ import annotations

import pytest

import brokers.providers.dhan
import brokers.providers.paper
import brokers.providers.upstox  # noqa: F401
from domain.market.segment_registry import registered_broker_ids, segment_mapper_for
from domain.types import ExchangeSegment


@pytest.mark.parametrize("broker_id", ["dhan", "upstox", "paper"])
def test_segment_mapper_registered(broker_id: str) -> None:
    mapper = segment_mapper_for(broker_id)
    assert mapper.broker_id == broker_id
    wire = mapper.to_wire(ExchangeSegment.NSE)
    assert isinstance(wire, str) and wire


def test_registered_broker_ids_includes_plugins() -> None:
    ids = registered_broker_ids()
    assert {"dhan", "upstox", "paper"} <= ids


def test_unknown_broker_raises_lookup_error() -> None:
    with pytest.raises(LookupError, match="No SegmentMapper registered"):
        segment_mapper_for("nonexistent_broker_xyz")
