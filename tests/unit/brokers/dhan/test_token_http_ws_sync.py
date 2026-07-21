"""Token refresh propagates to registered WS receivers via ConnectionTokenManager."""

from __future__ import annotations

from brokers.dhan.streaming.connection import DhanConnection
from tests.support.brokers.dhan.fixtures import FakeHttpClient, SAMPLE_ROWS


def test_broadcast_token_reaches_market_feed_receiver():
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)

    received: list[str] = []

    def _receiver(token: str) -> None:
        received.append(token)

    conn.register_token_receiver(_receiver)
    conn.broadcast_token("NEW-TOKEN")

    assert received == ["NEW-TOKEN"]
