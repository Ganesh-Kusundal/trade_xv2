"""Fail-closed tick drop signaling for Upstox (MD-3)."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer


class _Frame:
    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.type = "ltpc"


def test_invalid_quote_drop_emits_market_data_degraded() -> None:
    bus = MagicMock()
    mux = UpstoxMarketDataV3Multiplexer(
        authorizer=MagicMock(),
        event_bus=bus,
        degrade_every_n_drops=1,
    )
    frame = _Frame({"instrument_key": "NSE_EQ|X", "ltp": 0, "symbol": "BAD"})

    assert mux._tick_quote_is_valid(frame) is False
    mux._record_tick_drop(frame, "invalid_quote")

    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.event_type == "MARKET_DATA_DEGRADED"
    assert event.payload.get("degraded") is True
    assert event.payload.get("reason") == "invalid_quote"


def test_bus_translation_failure_emits_degraded() -> None:
    bus = MagicMock()
    mux = UpstoxMarketDataV3Multiplexer(
        authorizer=MagicMock(),
        event_bus=bus,
        degrade_every_n_drops=1,
    )
    mux._publish_tick_to_bus(_Frame(None))

    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.event_type == "MARKET_DATA_DEGRADED"
