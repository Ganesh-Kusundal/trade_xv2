"""Gateway-public probing: does connect() + data endpoints work end-to-end?

Verifies the Gateway facade (the only sanctioned entry point) correctly:
  * connect() establishes connectivity (sets _connected, starts schedulers)
  * ltp() / get_quote() / depth() / history() resolve the symbol via the
    wire and hit the correct broker endpoint through the connection adapters
  * NO network, NO internal (connection/adapters/wire) calls — only the
    public Gateway API is exercised.

Mirrors the existing broker-test fixtures (FakeTransport + pre-registered wire)
so the instrument master is bypassed (already covered by autoload tests).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from domain.entities import Bar, MarketDepth, Quote
from domain.value_objects import InstrumentId, Price, TimeFrame
from plugins.brokers.common.transport import BaseTransport
from plugins.brokers.dhan.gateway import DhanGateway
from plugins.brokers.upstox.gateway import UpstoxGateway


class _FakeTransport(BaseTransport):
    """Records calls; returns responses registered per path (or per prefix)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._responses: dict[str, Any] = {}

    def set_response(self, path: str, response: Any) -> None:
        self._responses[path] = response

    def _match(self, path: str) -> Any:
        if path in self._responses:
            return self._responses[path]
        # prefix match (e.g. /historical-candle/...)
        for key, val in self._responses.items():
            if path.startswith(key):
                return val
        return {}

    def get(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("GET", path, kwargs))
        return self._match(path)

    def post(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("POST", path, kwargs))
        return self._match(path)

    def put(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("PUT", path, kwargs))
        return self._match(path)

    def delete(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("DELETE", path, kwargs))
        return self._match(path)

    def calls_for(self, method: str, path: str) -> list[tuple[str, str, dict[str, Any]]]:
        return [c for c in self.calls if c[0] == method and path in c[1]]


# ---------------------------------------------------------------------------
# Dhan — connect() + all four data endpoints via the Gateway public surface
# ---------------------------------------------------------------------------


@pytest.fixture
def dhan_gateway() -> DhanGateway:
    from plugins.brokers.dhan.config import DhanConfig

    transport = _FakeTransport()
    gw = DhanGateway(
        config=DhanConfig(allow_live_orders=True),
        transport=transport,
    )
    # Pre-register the symbol on the wire (master-load path is covered elsewhere).
    gw.connection.wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    gw.connection.wire.register_security(InstrumentId.parse("NSE:TCS"), "11536")
    return gw


def test_dhan_connect_sets_connected(dhan_gateway: DhanGateway) -> None:
    assert dhan_gateway.connection._connected is False
    dhan_gateway.connect()
    assert dhan_gateway.connection._connected is True
    dhan_gateway.close()


def test_dhan_ltp_hits_marketfeed_and_returns_price(
    dhan_gateway: DhanGateway,
) -> None:
    dhan_gateway.connect()
    transport = dhan_gateway.connection.transport
    transport.set_response(
        "/marketfeed/ltp",
        {"data": {"NSE_EQ": {"2885": {"last_price": 2501.25}}}},
    )
    price = dhan_gateway.ltp(InstrumentId.parse("NSE:RELIANCE"))
    assert isinstance(price, Price)
    assert price.value == Decimal("2501.25")
    assert transport.calls_for("POST", "/marketfeed/ltp")
    dhan_gateway.close()


def test_dhan_get_quote_hits_marketfeed(dhan_gateway: DhanGateway) -> None:
    dhan_gateway.connect()
    transport = dhan_gateway.connection.transport
    transport.set_response(
        "/marketfeed/quote",
        {"data": {"NSE_EQ": {"2885": {"last_price": 2502.0, "depth": {}}}}},
    )
    quote = dhan_gateway.get_quote(InstrumentId.parse("NSE:RELIANCE"))
    assert isinstance(quote, Quote)
    assert transport.calls_for("POST", "/marketfeed/quote")
    dhan_gateway.close()


def test_dhan_depth_hits_marketfeed(dhan_gateway: DhanGateway) -> None:
    dhan_gateway.connect()
    transport = dhan_gateway.connection.transport
    transport.set_response(
        "/marketfeed/quote",
        {"data": {"NSE_EQ": {"2885": {"last_price": 2503.0, "depth": {}}}}},
    )
    depth = dhan_gateway.depth(InstrumentId.parse("NSE:RELIANCE"))
    assert isinstance(depth, MarketDepth)
    assert transport.calls_for("POST", "/marketfeed/quote")
    dhan_gateway.close()


def test_dhan_history_daily_hits_charts_historical(
    dhan_gateway: DhanGateway,
) -> None:
    dhan_gateway.connect()
    transport = dhan_gateway.connection.transport
    transport.set_response(
        "/charts/historical",
        {
            "data": [
                {"timestamp": "2024-01-01", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 1000},
                {"timestamp": "2024-01-02", "open": 105, "high": 115, "low": 100, "close": 112, "volume": 1200},
            ]
        },
    )
    bars = dhan_gateway.history(
        InstrumentId.parse("NSE:RELIANCE"),
        TimeFrame(value="day"),
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    assert isinstance(bars, list)
    assert all(isinstance(b, Bar) for b in bars)
    assert len(bars) == 2
    assert transport.calls_for("POST", "/charts/historical")
    dhan_gateway.close()


def test_dhan_missing_symbol_raises(dhan_gateway: DhanGateway) -> None:
    dhan_gateway.connect()
    with pytest.raises(Exception):
        dhan_gateway.ltp(InstrumentId.parse("NSE:UNKNOWN"))
    dhan_gateway.close()


# ---------------------------------------------------------------------------
# Upstox — connect() + all four data endpoints via the Gateway public surface
# ---------------------------------------------------------------------------


@pytest.fixture
def upstox_gateway() -> UpstoxGateway:
    from plugins.brokers.upstox.config import UpstoxConfig

    transport = _FakeTransport()
    gw = UpstoxGateway(
        config=UpstoxConfig(allow_live_orders=True),
        transport=transport,
    )
    gw.connection.wire.register_key(
        InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE"
    )
    return gw


def test_upstox_connect_sets_connected(upstox_gateway: UpstoxGateway) -> None:
    assert upstox_gateway.connection._connected is False
    upstox_gateway.connect()
    assert upstox_gateway.connection._connected is True
    upstox_gateway.close()


def test_upstox_ltp_hits_market_quote(upstox_gateway: UpstoxGateway) -> None:
    upstox_gateway.connect()
    transport = upstox_gateway.connection.transport
    transport.set_response(
        "/market-quote/ltp",
        {"data": {"NSE_EQ:RELIANCE": {"last_price": 2600.5}}},
    )
    price = upstox_gateway.ltp(InstrumentId.parse("NSE:RELIANCE"))
    assert isinstance(price, Price)
    assert price.value == Decimal("2600.5")
    assert transport.calls_for("GET", "/market-quote/ltp")
    upstox_gateway.close()


def test_upstox_get_quote_hits_market_quote(upstox_gateway: UpstoxGateway) -> None:
    upstox_gateway.connect()
    transport = upstox_gateway.connection.transport
    transport.set_response(
        "/market-quote/quotes",
        {"data": {"NSE_EQ:RELIANCE": {"last_price": 2601.0, "depth": {}}}},
    )
    quote = upstox_gateway.get_quote(InstrumentId.parse("NSE:RELIANCE"))
    assert isinstance(quote, Quote)
    assert transport.calls_for("GET", "/market-quote/quotes")
    upstox_gateway.close()


def test_upstox_depth_hits_market_quote(upstox_gateway: UpstoxGateway) -> None:
    upstox_gateway.connect()
    transport = upstox_gateway.connection.transport
    transport.set_response(
        "/market-quote/quotes",
        {"data": {"NSE_EQ:RELIANCE": {"last_price": 2602.0, "depth": {}}}},
    )
    depth = upstox_gateway.depth(InstrumentId.parse("NSE:RELIANCE"))
    assert isinstance(depth, MarketDepth)
    assert transport.calls_for("GET", "/market-quote/quotes")
    upstox_gateway.close()


def test_upstox_history_day_hits_historical_candle(
    upstox_gateway: UpstoxGateway,
) -> None:
    upstox_gateway.connect()
    transport = upstox_gateway.connection.transport
    transport.set_response(
        "/historical-candle/",
        {
            "data": {
                "candles": [
                    [1704066600, 100, 110, 95, 105, 1000],
                    [1704153000, 105, 115, 100, 112, 1200],
                ]
            }
        },
    )
    bars = upstox_gateway.history(
        InstrumentId.parse("NSE:RELIANCE"),
        TimeFrame(value="day"),
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    assert isinstance(bars, list)
    assert all(isinstance(b, Bar) for b in bars)
    assert len(bars) == 2
    assert transport.calls_for("GET", "/historical-candle/")
    upstox_gateway.close()


# ---------------------------------------------------------------------------
# Task 3 regression: connect() must NOT block on a cold-cache download
# ---------------------------------------------------------------------------


def test_dhan_connect_returns_without_blocking(tmp_path, monkeypatch) -> None:
    """connect() fires the warm-load in a background thread; the caller
    returns immediately even if the master download would block."""
    import time

    from plugins.brokers.dhan.config import DhanConfig

    transport = _FakeTransport()
    gw = DhanGateway(config=DhanConfig(allow_live_orders=True), transport=transport)

    # Simulate a cold cache: the warm-load blocks 2s downloading.
    loaded: list[float] = []

    def _slow_warm(*args, **kwargs) -> None:
        time.sleep(2.0)
        loaded.append(time.monotonic())

    monkeypatch.setattr(gw.connection, "ensure_fresh", _slow_warm)

    start = time.monotonic()
    gw.connect()  # must return quickly, not after 2s
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"connect() blocked for {elapsed:.2f}s"
    # Background warm-load eventually runs.
    assert gw.connection._connected is True
    for _ in range(40):
        if loaded:
            break
        time.sleep(0.1)
    assert loaded, "background warm-load never ran"
    gw.close()


def test_upstox_connect_returns_without_blocking(tmp_path, monkeypatch) -> None:
    import threading  # noqa: F401 (kept for parity with dhan test)
    import time

    from plugins.brokers.upstox.config import UpstoxConfig

    transport = _FakeTransport()
    gw = UpstoxGateway(config=UpstoxConfig(allow_live_orders=True), transport=transport)

    loaded: list[float] = []

    def _slow_warm(*args, **kwargs) -> None:
        time.sleep(2.0)
        loaded.append(time.monotonic())

    monkeypatch.setattr(gw.connection, "ensure_fresh", _slow_warm)

    start = time.monotonic()
    gw.connect()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"connect() blocked for {elapsed:.2f}s"
    assert gw.connection._connected is True
    for _ in range(40):
        if loaded:
            break
        time.sleep(0.1)
    assert loaded
    gw.close()
