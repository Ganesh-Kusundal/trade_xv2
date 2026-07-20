"""Regression: Dhan _transform_quote prefers exchange time over wall clock."""

from __future__ import annotations

from datetime import datetime, timezone

from brokers.dhan.websocket._helpers import _transform_quote


def test_transform_quote_uses_last_traded_time():
    exchange_ts = 1_718_601_600  # 2024-06-17T05:20:00Z
    result = _transform_quote(
        {
            "security_id": "2885",
            "last_price": "2450.55",
            "last_traded_time": exchange_ts,
        }
    )
    expected = datetime.fromtimestamp(exchange_ts, tz=timezone.utc)
    assert result["timestamp"] == expected


def test_transform_quote_falls_back_to_wall_clock_when_exchange_time_missing():
    before = datetime.now(timezone.utc)
    result = _transform_quote({"security_id": "2885", "last_price": "100.0"})
    after = datetime.now(timezone.utc)
    assert before <= result["timestamp"] <= after


def test_transform_quote_prefers_last_traded_time_over_exchange_timestamp():
    ltt = 1_700_000_000
    exch_ms = 1_700_000_000_000
    result = _transform_quote(
        {
            "security_id": "2885",
            "last_price": "100.0",
            "last_traded_time": ltt,
            "exchange_timestamp": exch_ms,
        }
    )
    assert result["timestamp"] == datetime.fromtimestamp(ltt, tz=timezone.utc)
