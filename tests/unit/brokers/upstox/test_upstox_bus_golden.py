"""TRANS-P5-010 — Upstox golden fixture EventBus TICK certification."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
from domain import Quote

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "upstox_bus_ticks.json"


class _Frame:
    def __init__(self, payload: dict, frame_type: str = "ltpc") -> None:
        self.payload = payload
        self.type = frame_type


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.unit
@pytest.mark.certification
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_upstox_bus_golden_tick_shape(case: dict) -> None:
    bus = MagicMock()
    mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock(), event_bus=bus)
    frame = _Frame(case["payload"], frame_type=case.get("frame_type", "ltpc"))

    mux._publish_tick_to_bus(frame)

    expected = case["expected"]
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.event_type == expected["event_type"]
    assert event.source == expected["source"]
    quote = event.payload["quote"]
    assert isinstance(quote, Quote)
    assert quote.symbol == expected["symbol"]
    assert str(quote.ltp) == expected["ltp"] or quote.ltp == Decimal(expected["ltp"])
    assert mux.published_ticks == 1
    assert mux.dropped_bus_ticks == 0
