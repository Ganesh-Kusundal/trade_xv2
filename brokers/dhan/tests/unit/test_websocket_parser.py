"""Tests for DhanMessageParser — pure message transformation logic."""

from __future__ import annotations

import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

import pytest

from brokers.dhan.ws_parser import DhanMessageParser


class FakeResolver:
    """Minimal resolver that maps security_id → symbol."""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    def get_by_security_id(self, security_id: str):
        symbol = self._mapping.get(str(security_id))
        if symbol:
            return type("FakeInst", (), {"symbol": symbol})()
        return None


class TestTransformQuote:
    """Verify quote transformation from SDK dict to canonical dict."""

    def test_transform_quote_basic_fields(self):
        """Basic quote transformation must produce correct canonical dict."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Quote Data",
            "security_id": 2885,
            "last_price": "2450.50",
            "open": "2440.00",
            "high": "2460.00",
            "low": "2435.00",
            "close": "2445.00",
            "volume": 1234567,
        }
        result = parser.transform_quote(raw)
        assert result["symbol"] == "2885"
        assert result["security_id"] == "2885"
        assert result["ltp"] == Decimal("2450.50")
        assert result["open"] == Decimal("2440.00")
        assert result["high"] == Decimal("2460.00")
        assert result["low"] == Decimal("2435.00")
        assert result["close"] == Decimal("2445.00")
        assert result["volume"] == 1234567
        assert result["change"] == Decimal("0")

    def test_transform_quote_with_ltp_key(self):
        """Must handle LTP key (uppercase) from SDK."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Ticker Data",
            "security_id": 2885,
            "LTP": "1500.00",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": 0,
        }
        result = parser.transform_quote(raw)
        assert result["ltp"] == Decimal("1500.00")
        assert result["open"] is None
        assert result["volume"] == 0

    def test_transform_quote_with_resolver(self):
        """Must resolve symbol from security_id when resolver is provided."""
        resolver = FakeResolver({"2885": "RELIANCE"})
        parser = DhanMessageParser(resolver=resolver)
        raw = {
            "type": "Quote Data",
            "security_id": 2885,
            "last_price": "2450.50",
            "open": "2440.00",
            "high": "2460.00",
            "low": "2435.00",
            "close": "2445.00",
            "volume": 100,
        }
        result = parser.transform_quote(raw)
        assert result["symbol"] == "RELIANCE"
        assert result["security_id"] == "2885"

    def test_transform_quote_resolver_exception(self):
        """Must fall back to security_id when resolver raises."""
        class BadResolver:
            def get_by_security_id(self, sid):
                raise RuntimeError("resolver failure")

        parser = DhanMessageParser(resolver=BadResolver())
        raw = {
            "type": "Quote Data",
            "security_id": 9999,
            "last_price": "100.00",
            "open": "100.00",
            "high": "100.00",
            "low": "100.00",
            "close": "100.00",
            "volume": 1,
        }
        result = parser.transform_quote(raw)
        assert result["symbol"] == "9999"

    def test_transform_quote_missing_security_id(self):
        """Must handle missing security_id gracefully."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Quote Data",
            "last_price": "100.00",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": 0,
        }
        result = parser.transform_quote(raw)
        assert result["symbol"] == ""
        assert result["security_id"] == ""

    def test_transform_quote_numeric_strings(self):
        """Must handle numeric string values for all price fields."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Quote Data",
            "security_id": 1234,
            "last_price": "0",
            "open": "0",
            "high": "0",
            "low": "0",
            "close": "0",
            "volume": "5000",
        }
        result = parser.transform_quote(raw)
        assert result["ltp"] == Decimal("0")
        assert result["volume"] == 5000

    def test_transform_quote_none_values(self):
        """Must handle None values for optional price fields."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Quote Data",
            "security_id": 1234,
            "last_price": "100",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": 0,
        }
        result = parser.transform_quote(raw)
        assert result["open"] is None
        assert result["high"] is None
        assert result["low"] is None
        assert result["close"] is None


class TestTransformDepth:
    """Verify depth transformation from SDK dict to canonical dict."""

    def test_transform_depth_basic(self):
        """Basic depth transformation must produce correct canonical dict."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Market Depth",
            "security_id": 2885,
            "last_price": "2450.50",
            "depth": {
                "bids": [{"price": "2450.00", "quantity": 100, "orders": 5}],
                "asks": [{"price": "2451.00", "quantity": 50, "orders": 3}],
            },
        }
        result = parser.transform_depth(raw)
        assert result["symbol"] == "2885"
        assert result["security_id"] == "2885"
        assert result["ltp"] == Decimal("2450.50")
        assert result["depth"] == raw["depth"]

    def test_transform_depth_with_resolver(self):
        """Must resolve symbol from security_id when resolver is provided."""
        resolver = FakeResolver({"2885": "RELIANCE"})
        parser = DhanMessageParser(resolver=resolver)
        raw = {
            "type": "Market Depth",
            "security_id": 2885,
            "last_price": "2450.50",
            "depth": {"bids": [], "asks": []},
        }
        result = parser.transform_depth(raw)
        assert result["symbol"] == "RELIANCE"

    def test_transform_depth_empty_depth_field(self):
        """Must handle missing or empty depth field."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Market Depth",
            "security_id": 2885,
            "last_price": "2450.50",
        }
        result = parser.transform_depth(raw)
        assert result["depth"] == []

    def test_transform_depth_list_format(self):
        """Must handle depth as list (legacy SDK format)."""
        parser = DhanMessageParser(resolver=None)
        raw = {
            "type": "Market Data",
            "security_id": 2885,
            "last_price": "2450.50",
            "depth": [
                {"bid_quantity": 100, "ask_quantity": 50, "bid_price": "2450.00", "ask_price": "2451.00"},
            ],
        }
        result = parser.transform_depth(raw)
        assert len(result["depth"]) == 1


class TestParseMessageType:
    """Verify message type classification."""

    def test_classify_ticker(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type("Ticker Data") == "TICKER"

    def test_classify_quote(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type("Quote Data") == "QUOTE"

    def test_classify_market_depth(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type("Market Depth") == "DEPTH"

    def test_classify_full_data(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type("Full Data") == "FULL"

    def test_classify_unknown_type(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type("Unknown Type") == "UNKNOWN"

    def test_classify_missing_type(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type("") == "UNKNOWN"

    def test_classify_none_type(self):
        parser = DhanMessageParser(resolver=None)
        assert parser.classify_message_type(None) == "UNKNOWN"


class TestParserThreadSafety:
    """Verify parser is thread-safe (uses RLock for resolver calls)."""

    def test_concurrent_transform_calls(self):
        """Multiple threads calling transform_quote must not deadlock."""
        import threading

        resolver = FakeResolver({"2885": "RELIANCE", "2886": "INFY"})
        parser = DhanMessageParser(resolver=resolver)

        results = []
        errors = []

        def transform_thread(security_id, symbol_expected):
            try:
                raw = {
                    "type": "Quote Data",
                    "security_id": security_id,
                    "last_price": "100.00",
                    "open": "100.00",
                    "high": "100.00",
                    "low": "100.00",
                    "close": "100.00",
                    "volume": 1,
                }
                result = parser.transform_quote(raw)
                results.append(result["symbol"] == symbol_expected)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(10):
            t1 = threading.Thread(target=transform_thread, args=(2885, "RELIANCE"))
            t2 = threading.Thread(target=transform_thread, args=(2886, "INFY"))
            threads.extend([t1, t2])

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0
        assert all(results)
