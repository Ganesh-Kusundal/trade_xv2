"""Fail-closed tick drop signaling (MD-3)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.dhan.websocket.publish import MarketFeedPublisher


def test_drop_emits_market_data_degraded_event() -> None:
    bus = MagicMock()
    pub = MarketFeedPublisher(
        bus,
        next_sequence=lambda _s: 1,
        to_decimal=lambda x: Decimal(str(x or 0)),
        degrade_every_n_drops=1,
    )
    pub.publish_tick({"symbol": "RELIANCE", "ltp": 0})
    bus.publish.assert_called_once()
    event = bus.publish.call_args[0][0]
    assert event.event_type == "MARKET_DATA_DEGRADED"
    assert event.payload.get("degraded") is True