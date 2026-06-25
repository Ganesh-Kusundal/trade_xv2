"""Tests for UpstoxBrokerGateway.stream() and canonical Quote translation.

Covers:
- subscription wiring (already-connected / disconnected paths)
- ``_translate_tick_to_quote`` for both dict and attribute-style payloads
- ``_canonical_symbol_for_defn`` symbol priority
- fall-through when instrument_key cannot be resolved
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from brokers.upstox.gateway import UpstoxBrokerGateway
from domain import Quote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockWebsocket:
    def __init__(self, connected: bool = False) -> None:
        self._connected = connected
        self.subscribed: list[tuple[list[str], str]] = []
        self.listeners: list[Callable[[str, Any], None]] = []
        self.connect_called = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def subscribe(self, keys: list[str], mode: str) -> None:
        self.subscribed.append((keys, mode))

    def add_listener(self, listener: Callable[[str, Any], None]) -> None:
        self.listeners.append(listener)

    async def connect(self) -> None:
        self.connect_called = True
        self._connected = True


def _make_gateway(
    connected: bool = False,
    resolver_defn: Any = None,
) -> tuple[UpstoxBrokerGateway, _MockWebsocket, MagicMock]:
    ws = _MockWebsocket(connected=connected)
    broker = MagicMock()
    broker.market_data_websocket = ws

    # Configure the resolver mock
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = resolver_defn
    broker.instrument_resolver = mock_resolver

    gateway = UpstoxBrokerGateway(broker)
    return gateway, ws, broker


def _make_defn(
    name: str = "",
    symbol: str = "",
    trading_symbol: str = "",
    instrument_key: str = "",
) -> MagicMock:
    defn = MagicMock()
    defn.name = name
    defn.symbol = symbol
    defn.trading_symbol = trading_symbol
    defn.instrument_key = instrument_key
    return defn


# ---------------------------------------------------------------------------
# Stream subscription wiring
# ---------------------------------------------------------------------------


class TestUpstoxGatewayStream:
    def test_stream_subscribes_when_already_connected(self):
        gateway, ws, _broker = _make_gateway(connected=True)

        gateway.stream("INFY", exchange="NSE", mode="LTP")

        assert not ws.connect_called
        assert len(ws.subscribed) == 1
        keys, mode = ws.subscribed[0]
        assert keys == ["NSE|INFY"]
        assert mode == "ltp"

    def test_stream_connects_when_not_connected(self):
        gateway, ws, _broker = _make_gateway(connected=False)

        gateway.stream("INFY", exchange="NSE", mode="LTP")

        assert ws.connect_called
        assert len(ws.subscribed) == 1
        keys, mode = ws.subscribed[0]
        assert keys == ["NSE|INFY"]
        assert mode == "ltp"

    def test_stream_wraps_on_tick_to_quote(self):
        """on_tick receives a Quote object, not the raw broker payload."""
        gateway, ws, _broker = _make_gateway(connected=True)

        received: list[Any] = []

        def on_tick(tick: Any) -> None:
            received.append(tick)

        gateway.stream("INFY", exchange="NSE", mode="LTP", on_tick=on_tick)

        assert len(ws.listeners) == 1
        listener = ws.listeners[0]

        # Simulate a raw tick from the multiplexer (no instrument_key → raw passthrough)
        listener("tick", {"frame_type": "ltpc", "payload": {"last_price": 1800.0}})

        assert len(received) == 1
        # No instrument_key in the payload → raw dict is forwarded
        assert isinstance(received[0], dict)

    def test_stream_wraps_on_tick_resolves_quote(self):
        """When instrument_key resolves, on_tick receives a canonical Quote."""
        defn = _make_defn(name="INFY", instrument_key="NSE_EQ|INFY")
        gateway, ws, _broker = _make_gateway(connected=True, resolver_defn=defn)

        received: list[Any] = []
        gateway.stream("INFY", exchange="NSE", mode="LTP", on_tick=received.append)

        listener = ws.listeners[0]
        listener(
            "tick",
            {
                "frame_type": "ltpc",
                "payload": {
                    "instrument_key": "NSE_EQ|INFY",
                    "last_price": 1800.5,
                    "close_price": 1780.0,
                    "volume": 5000,
                },
            },
        )

        assert len(received) == 1
        q = received[0]
        assert isinstance(q, Quote)
        assert q.symbol == "INFY"
        assert q.ltp == Decimal("1800.5")
        assert q.close == Decimal("1780.0")
        assert q.volume == 5000
        assert q.change == Decimal("1800.5") - Decimal("1780.0")

    def test_stream_maps_exchange_segment(self):
        gateway, ws, _broker = _make_gateway(connected=True)

        gateway.stream("RELIANCE", exchange="BSE", mode="FULL")

        keys, mode = ws.subscribed[0]
        assert keys == ["BSE|RELIANCE"]
        assert mode == "full"

    def test_stream_accepts_on_tick_none(self):
        gateway, ws, _broker = _make_gateway(connected=True)

        result = gateway.stream("INFY", exchange="NSE", mode="LTP")

        assert result is ws
        assert ws.listeners == []

    def test_stream_connects_async_when_loop_running(self):
        async def _inner() -> None:
            gateway, ws, _broker = _make_gateway(connected=False)
            gateway.stream("INFY", exchange="NSE", mode="LTP")
            # Give the scheduled coroutine time to execute
            await asyncio.sleep(0.05)
            assert ws.connect_called

        asyncio.run(_inner())


# ---------------------------------------------------------------------------
# _translate_tick_to_quote
# ---------------------------------------------------------------------------


class TestTranslateTickToQuote:
    def test_dict_payload_with_instrument_key_resolved(self):
        defn = _make_defn(
            name="NIFTY 22 MAY 25 24000 CE", instrument_key="NSE_FO|NIFTY22MAY2524000CE"
        )
        gateway, _ws, _broker = _make_gateway(resolver_defn=defn)

        raw = {
            "frame_type": "full",
            "payload": {
                "instrument_key": "NSE_FO|NIFTY22MAY2524000CE",
                "last_price": 250.5,
                "close_price": 230.0,
                "volume": 12000,
                "best_bid_price": 250.0,
                "best_ask_price": 251.0,
            },
        }
        q = gateway._translate_tick_to_quote(raw)

        assert isinstance(q, Quote)
        assert q.symbol == "NIFTY 22 MAY 25 24000 CE"
        assert q.ltp == Decimal("250.5")
        assert q.bid == Decimal("250.0")
        assert q.ask == Decimal("251.0")

    def test_dict_payload_missing_instrument_key_returns_raw(self):
        gateway, _ws, _broker = _make_gateway()

        raw = {"frame_type": "ltpc", "payload": {"last_price": 100.0}}
        result = gateway._translate_tick_to_quote(raw)

        assert result is raw

    def test_dict_payload_unresolvable_key_falls_back_to_rhs(self):
        """When resolver returns None, symbol is extracted from the key RHS."""
        gateway, _ws, broker = _make_gateway()
        broker.instrument_resolver.resolve.return_value = None

        raw = {
            "frame_type": "ltpc",
            "payload": {
                "instrument_key": "NSE_EQ|RELIANCE",
                "last_price": 2900.0,
            },
        }
        q = gateway._translate_tick_to_quote(raw)

        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2900.0")

    def test_attribute_payload_protobuf_style(self):
        """Protobuf-decoded objects expose fields via attributes, not dict keys."""
        defn = _make_defn(symbol="RELIANCE", instrument_key="NSE_EQ|RELIANCE")
        gateway, _ws, _broker = _make_gateway(resolver_defn=defn)

        payload = MagicMock()
        payload.instrument_key = "NSE_EQ|RELIANCE"
        payload.instrumentKey = ""
        payload.last_price = 2900.0
        payload.ltp = 0
        payload.close_price = 2850.0
        payload.close = 0
        payload.prev_close_price = 0
        payload.ohlc = None
        payload.open = 0
        payload.high = 0
        payload.low = 0
        payload.volume = 10000
        payload.total_buy_quantity = 0
        payload.total_sell_quantity = 0
        payload.best_bid_price = 0
        payload.best_ask_price = 0
        payload.exchange_timestamp = None
        # Make attribute access work like a real object (not dict)
        payload.__class__ = object.__class__  # ensures isinstance(payload, dict) is False

        raw = {"frame_type": "ltpc", "payload": payload}
        q = gateway._translate_tick_to_quote(raw)

        assert isinstance(q, Quote)
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2900.0")

    def test_none_payload_returns_raw(self):
        gateway, _ws, _broker = _make_gateway()
        raw = {"frame_type": "ltpc", "payload": None}
        result = gateway._translate_tick_to_quote(raw)
        assert result is raw

    def test_ohlc_dict_extracted(self):
        defn = _make_defn(symbol="NIFTY50", instrument_key="NSE_INDEX|NIFTY50")
        gateway, _ws, _broker = _make_gateway(resolver_defn=defn)

        raw = {
            "frame_type": "full",
            "payload": {
                "instrument_key": "NSE_INDEX|NIFTY50",
                "last_price": 22500.0,
                "close_price": 22000.0,
                "ohlc": {"open": 22100.0, "high": 22600.0, "low": 22050.0, "close": 22450.0},
                "volume": 0,
            },
        }
        q = gateway._translate_tick_to_quote(raw)

        assert q.open == Decimal("22100.0")
        assert q.high == Decimal("22600.0")
        assert q.low == Decimal("22050.0")
        assert q.close == Decimal("22450.0")  # OHLC close takes priority

    def test_timestamp_millis_converted(self):
        defn = _make_defn(symbol="TCS", instrument_key="NSE_EQ|TCS")
        gateway, _ws, _broker = _make_gateway(resolver_defn=defn)

        from datetime import datetime, timezone

        ts_ms = int(datetime(2025, 5, 20, 9, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)

        raw = {
            "frame_type": "ltpc",
            "payload": {
                "instrument_key": "NSE_EQ|TCS",
                "last_price": 3500.0,
                "close_price": 3480.0,
                "exchange_timestamp": ts_ms,
                "volume": 0,
            },
        }
        q = gateway._translate_tick_to_quote(raw)

        assert q.timestamp is not None
        assert q.timestamp.year == 2025
        assert q.timestamp.month == 5
        assert q.timestamp.day == 20


# ---------------------------------------------------------------------------
# _canonical_symbol_for_defn
# ---------------------------------------------------------------------------


class TestCanonicalSymbolForDefn:
    def test_name_takes_priority(self):
        defn = _make_defn(
            name="NIFTY 29 MAY 25 24800 CE",
            symbol="NIFTY2924800CE",
            trading_symbol="NIFTY2924800CE",
        )
        sym = UpstoxBrokerGateway._canonical_symbol_for_defn(defn, "NSE_FO|NIFTY2924800CE")
        assert sym == "NIFTY 29 MAY 25 24800 CE"

    def test_symbol_used_when_name_empty(self):
        defn = _make_defn(name="", symbol="RELIANCE", trading_symbol="RELIANCE-EQ")
        sym = UpstoxBrokerGateway._canonical_symbol_for_defn(defn, "NSE_EQ|RELIANCE")
        assert sym == "RELIANCE"

    def test_trading_symbol_fallback(self):
        defn = _make_defn(name="", symbol="", trading_symbol="TCS-EQ")
        sym = UpstoxBrokerGateway._canonical_symbol_for_defn(defn, "NSE_EQ|TCS")
        assert sym == "TCS-EQ"

    def test_instrument_key_rhs_fallback_when_no_defn(self):
        sym = UpstoxBrokerGateway._canonical_symbol_for_defn(None, "NSE_EQ|HDFC")
        assert sym == "HDFC"

    def test_bare_key_when_no_pipe(self):
        sym = UpstoxBrokerGateway._canonical_symbol_for_defn(None, "UNKNOWN")
        assert sym == "UNKNOWN"

    def test_empty_fallback_key(self):
        sym = UpstoxBrokerGateway._canonical_symbol_for_defn(None, "")
        assert sym == ""
