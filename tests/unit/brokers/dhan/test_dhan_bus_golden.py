"""TOS-P5-020 — Dhan golden fixture EventBus TICK certification."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brokers.providers.dhan.websocket.publish import MarketFeedPublisher
from domain import Quote

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "dhan_bus_ticks.json"


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["cases"]


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


@pytest.mark.unit
@pytest.mark.certification
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_dhan_bus_golden_tick_shape(case: dict) -> None:
    bus = MagicMock()
    seq = {"n": 0}

    def _next_sequence(symbol: str) -> int:
        seq["n"] += 1
        return seq["n"]

    pub = MarketFeedPublisher(bus, _next_sequence, to_decimal=_to_decimal)
    quote = dict(case["quote"])
    pub.publish_tick(quote)

    expected = case["expected"]
    if expected.get("dropped"):
        bus.publish.assert_not_called()
        assert pub.dropped_ticks >= 1
        assert pub.published_ticks == 0
        return

    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.event_type == expected["event_type"]
    assert event.source == expected["source"]
    q = event.payload["quote"]
    assert isinstance(q, Quote)
    assert q.symbol == expected["symbol"]
    assert q.ltp == Decimal(expected["ltp"])
    assert pub.published_ticks == 1
    assert pub.dropped_ticks == 0


@pytest.mark.unit
def test_dhan_publish_silent_when_bus_none() -> None:
    """Without a bus, publisher no-ops (paper/offline). Live must wire a bus."""
    pub = MarketFeedPublisher(None, lambda s: 1, to_decimal=_to_decimal)
    pub.publish_tick({"symbol": "RELIANCE", "ltp": 100})
    assert pub.published_ticks == 0
