"""Real WebSocket payload parsing tests.

Tests _transform_quote and _transform_depth with realistic broker
payloads (matching the actual JSON shape from Dhan WebSocket feeds)
rather than minimal mocked dicts.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.dhan.websocket import DhanMarketFeed


class TestRealDhanWebSocketPayloads:
    def _make_feed(self) -> DhanMarketFeed:
        return DhanMarketFeed(
            client_id="TEST",
            access_token="TOKEN",
            instruments=[],
        )

    def test_transform_quote_full_ticker_payload(self):
        feed = self._make_feed()
        payload = {
            "type": "Ticker Data",
            "security_id": "2885",
            "last_price": "2450.55",
            "last_traded_quantity": 100,
            "last_traded_time": 1718601600,
            "avg_traded_price": "2445.30",
            "total_traded_volume": 5000000,
            "open": "2430.00",
            "high": "2460.00",
            "low": "2420.50",
            "close": "2425.75",
            "change": 24.80,
            "net_change": "1.02",
        }
        result = feed._transform_quote(payload)
        assert result["ltp"] == Decimal("2450.55")
        assert result["open"] == Decimal("2430.00")
        assert result["high"] == Decimal("2460.00")
        assert result["low"] == Decimal("2420.50")
        assert result["close"] == Decimal("2425.75")
        assert result["security_id"] == "2885"

    def test_transform_quote_ltp_only_payload(self):
        feed = self._make_feed()
        payload = {
            "type": "Ticker Data",
            "security_id": "3045",
            "last_price": "1780.25",
            "last_traded_time": 1718601600,
        }
        result = feed._transform_quote(payload)
        assert result["ltp"] == Decimal("1780.25")
        assert result["open"] is None
        assert result["high"] is None
        assert result["low"] is None
        assert result["close"] is None

    def test_transform_quote_missing_last_price_fallback(self):
        feed = self._make_feed()
        payload = {
            "security_id": "2885",
            "LTP": "2450.55",
        }
        result = feed._transform_quote(payload)
        assert result["ltp"] == Decimal("2450.55")

    def test_transform_quote_zero_prices(self):
        feed = self._make_feed()
        payload = {
            "security_id": "2885",
            "last_price": "0",
            "open": "0",
            "high": "0",
            "low": "0",
            "close": "0",
        }
        result = feed._transform_quote(payload)
        assert result["ltp"] == Decimal("0")
        assert result["open"] == Decimal("0")
        assert result["high"] == Decimal("0")
        assert result["low"] == Decimal("0")
        assert result["close"] == Decimal("0")

    def test_transform_depth_full_5_level(self):
        feed = self._make_feed()
        depth_data = [
            {"price": "2450.00", "quantity": 100, "orders": 5},
            {"price": "2451.00", "quantity": 80, "orders": 4},
            {"price": "2449.50", "quantity": 200, "orders": 3},
            {"price": "2451.50", "quantity": 120, "orders": 2},
            {"price": "2449.00", "quantity": 150, "orders": 2},
        ]
        payload = {
            "security_id": "2885",
            "last_price": "2450.55",
            "depth": depth_data,
        }
        result = feed._transform_depth(payload)
        assert result["security_id"] == "2885"
        assert result["ltp"] == Decimal("2450.55")
        assert len(result["depth"]) == 5

    def test_transform_depth_empty_levels(self):
        feed = self._make_feed()
        payload = {
            "security_id": "2885",
            "depth": [],
        }
        result = feed._transform_depth(payload)
        assert result["security_id"] == "2885"
        assert result["depth"] == []

    def test_transform_quote_volume_as_int(self):
        feed = self._make_feed()
        payload = {
            "security_id": "2885",
            "last_price": "2450.55",
            "volume": 1234567,
        }
        result = feed._transform_quote(payload)
        assert result["volume"] == 1234567
        assert isinstance(result["volume"], int)

    def test_transform_quote_no_security_id(self):
        feed = self._make_feed()
        payload = {"last_price": "100"}
        result = feed._transform_quote(payload)
        assert result["security_id"] == ""
        assert result["ltp"] == Decimal("100")
