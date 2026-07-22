"""DepthKind enum completeness and MarketDepth typing."""

from __future__ import annotations

from datetime import datetime, timezone

from domain.entities.market import DepthKind, MarketDepth
from domain.events.types import EventType


def test_depth_kind_values_match_runtime_strings() -> None:
    assert DepthKind.DEPTH_5.value == "DEPTH_5"
    assert DepthKind.DEPTH_20.value == "DEPTH_20"
    assert DepthKind.DEPTH_30.value == "DEPTH_30"
    assert DepthKind.DEPTH_200.value == "DEPTH_200"


def test_event_type_has_depth_30() -> None:
    assert EventType.DEPTH_30 == "DEPTH_30"


def test_market_depth_depth_type_is_enum() -> None:
    md = MarketDepth(depth_type="DEPTH_20")
    assert md.depth_type is DepthKind.DEPTH_20


def test_market_depth_coerces_string_depth_type() -> None:
    md = MarketDepth(depth_type="DEPTH_30", timestamp=datetime.now(tz=timezone.utc))
    assert md.depth_type is DepthKind.DEPTH_30
