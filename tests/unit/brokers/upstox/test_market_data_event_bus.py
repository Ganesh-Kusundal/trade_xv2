"""Upstox V3 market feed EventBus publish (ADR-016 / AUDIT-003)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from domain import Quote
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer


class _Frame:
    def __init__(self, payload: dict, frame_type: str = "ltpc") -> None:
        self.payload = payload
        self.type = frame_type


def test_publish_tick_to_bus_emits_tick_event() -> None:
    bus = MagicMock()
    mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock(), event_bus=bus)
    frame = _Frame(
        {
            "instrument_key": "NSE_EQ|INE002A01018",
            "ltp": 100.5,
            "symbol": "RELIANCE",
        }
    )

    mux._publish_tick_to_bus(frame)

    assert mux.published_ticks == 1
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.event_type == "TICK"
    assert isinstance(event.payload["quote"], Quote)
    assert event.payload["quote"].ltp == Decimal("100.5")


def test_publish_tick_to_bus_noop_without_bus() -> None:
    mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock(), event_bus=None)
    frame = _Frame({"instrument_key": "NSE_EQ|X", "ltp": 10, "symbol": "X"})

    mux._publish_tick_to_bus(frame)

    assert mux.published_ticks == 0
    assert mux.dropped_bus_ticks == 0