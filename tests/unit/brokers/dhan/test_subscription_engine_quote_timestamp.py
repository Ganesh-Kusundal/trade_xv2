"""SubscriptionEngine passes broker timestamps into Quote DTOs."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.providers.dhan.market_data.subscription_engine import SubscriptionEngine
from domain.entities import Quote


def test_subscribe_market_wraps_quote_with_timestamp() -> None:
    conn = MagicMock()
    feed = MagicMock()
    feed.is_connected = False
    conn.market_feed = None
    conn.create_market_feed = MagicMock(return_value=feed)

    ref = MagicMock()
    ref.exchange_segment = "NSE_EQ"
    ref.security_id = "2885"
    conn.instruments.resolve_dhan_ref = MagicMock(return_value=ref)

    engine = SubscriptionEngine(conn)
    received: list[Quote] = []
    broker_ts = datetime(2026, 1, 15, 9, 15, tzinfo=timezone.utc)

    engine.subscribe_market("RELIANCE", "NSE", on_tick=received.append)

    assert feed.on_quote.called
    wrapper = feed.on_quote.call_args.args[0]
    wrapper(
        {
            "symbol": "RELIANCE",
            "ltp": Decimal("2500"),
            "volume": 100,
            "timestamp": broker_ts,
        }
    )

    assert len(received) == 1
    assert received[0].timestamp == broker_ts
