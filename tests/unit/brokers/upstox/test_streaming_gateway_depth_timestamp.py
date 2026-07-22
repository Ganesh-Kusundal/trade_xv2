"""StreamingGateway depth ticks preserve broker-reported timestamps."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.providers.upstox.adapters.streaming_gateway import StreamingGateway
from domain.entities.market import DepthKind, MarketDepth


def test_translate_tick_to_depth_uses_exchange_timestamp() -> None:
    gateway = StreamingGateway(MagicMock(), MagicMock(), lambda sym, exch: f"NSE_EQ|{sym}")
    expected = datetime(2025, 5, 20, 9, 15, tzinfo=timezone.utc)
    ts_ms = int(expected.timestamp() * 1000)

    depth = gateway._translate_tick_to_depth(
        {
            "exchange_timestamp": ts_ms,
            "depth": {
                "bids": [{"price": 1800.5, "quantity": 100, "orders": 2}],
                "asks": [{"price": 1801.0, "quantity": 200, "orders": 1}],
            },
        },
        "INFY",
    )

    assert isinstance(depth, MarketDepth)
    assert depth.timestamp == expected
    assert depth.depth_type == DepthKind.DEPTH_5
