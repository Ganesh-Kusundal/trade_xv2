"""Upstox regression suite manifest — P0 capability coverage."""

from __future__ import annotations

import contextlib
import threading
import time

from brokers.providers.upstox.wire import UpstoxWireAdapter
from tests.support.brokers.regression_manifest import RegressionCase


def _assert_nse_quote(gw: UpstoxWireAdapter) -> None:
    q = gw.quote("RELIANCE", "NSE")
    assert q.ltp > 0


def _assert_nse_ltp(gw: UpstoxWireAdapter) -> None:
    ltp = gw.ltp("RELIANCE", "NSE")
    assert ltp > 0


def _assert_nse_history(gw: UpstoxWireAdapter) -> None:
    df = gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
    assert df is not None and len(df) > 0
    for col in ("open", "high", "low", "close", "volume"):
        assert col in getattr(df, "columns", ()), f"Missing column: {col}"


def _assert_funds(gw: UpstoxWireAdapter) -> None:
    bal = gw.funds()
    assert bal is not None


def _assert_positions(gw: UpstoxWireAdapter) -> None:
    assert isinstance(gw.positions(), list)


def _assert_holdings(gw: UpstoxWireAdapter) -> None:
    assert isinstance(gw.holdings(), list)


def _assert_orderbook(gw: UpstoxWireAdapter) -> None:
    book = gw.get_orderbook() if hasattr(gw, "get_orderbook") else gw.orderbook()
    assert isinstance(book, list)


def _assert_search(gw: UpstoxWireAdapter) -> None:
    results = gw.search("RELIANCE")
    assert isinstance(results, list)
    assert len(results) >= 1


def _assert_depth(gw: UpstoxWireAdapter) -> None:
    depth = gw.depth("RELIANCE", "NSE")
    assert depth is not None
    assert len(depth.bids) >= 1 or len(depth.asks) >= 1


def _assert_option_chain(gw: UpstoxWireAdapter) -> None:
    chain = gw.option_chain("NIFTY", "NSE")
    assert chain is not None


def _assert_connection_status(gw: UpstoxWireAdapter) -> None:
    if not hasattr(gw, "get_connection_status"):
        return
    status = gw.get_connection_status()
    assert isinstance(status, dict)
    assert "portfolio_stream" in status


def _assert_portfolio_stream_capability(gw: UpstoxWireAdapter) -> None:
    from domain import Capability

    broker = gw._broker
    provider = broker.get_capability(Capability.PORTFOLIO_STREAM)
    assert provider is broker.portfolio_stream


def _assert_ltp_stream(gw: UpstoxWireAdapter) -> None:
    """LTP stream must receive ticks within 15 s during market hours."""
    received = threading.Event()
    ticks: list[object] = []

    def on_tick(q):
        ticks.append(q)
        received.set()

    feed = gw.stream("RELIANCE", "NSE", mode="LTP", on_tick=on_tick)
    try:
        got = received.wait(timeout=15)
        assert got and len(ticks) > 0, "LTP stream: 0 ticks in 15 s"
    finally:
        with contextlib.suppress(Exception):
            feed.disconnect()


def _assert_subscribe_normalizes_ticks(_gw) -> None:
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[5] / "src/brokers/providers/upstox/data_provider.py"
    ).read_text()
    assert "_normalize_quote(raw, instrument_id)" in text
    assert "callback(instrument_id, raw)" not in text


OFF_MARKET_CASES: tuple[RegressionCase, ...] = (
    RegressionCase(
        id="upstox.nse.quote",
        capability="quote",
        tier="off_market_safe",
        segment="NSE",
        description="NSE equity quote returns positive LTP",
        assert_fn=_assert_nse_quote,
    ),
    RegressionCase(
        id="upstox.nse.ltp",
        capability="ltp",
        tier="off_market_safe",
        segment="NSE",
        description="NSE equity LTP is positive",
        assert_fn=_assert_nse_ltp,
    ),
    RegressionCase(
        id="upstox.nse.history",
        capability="historical",
        tier="off_market_safe",
        segment="NSE",
        description="NSE daily history returns OHLCV bars",
        assert_fn=_assert_nse_history,
    ),
    RegressionCase(
        id="upstox.nfo.option_chain",
        capability="option_chain",
        tier="off_market_safe",
        segment="NFO",
        description="NIFTY option chain resolves",
        assert_fn=_assert_option_chain,
    ),
    RegressionCase(
        id="upstox.funds",
        capability="funds",
        tier="off_market_safe",
        segment="ACCOUNT",
        description="Funds endpoint returns balance",
        assert_fn=_assert_funds,
    ),
    RegressionCase(
        id="upstox.positions",
        capability="positions",
        tier="off_market_safe",
        segment="ACCOUNT",
        description="Positions endpoint returns list",
        assert_fn=_assert_positions,
    ),
    RegressionCase(
        id="upstox.holdings",
        capability="holdings",
        tier="off_market_safe",
        segment="ACCOUNT",
        description="Holdings endpoint returns list",
        assert_fn=_assert_holdings,
    ),
    RegressionCase(
        id="upstox.orderbook",
        capability="orderbook",
        tier="off_market_safe",
        segment="ACCOUNT",
        description="Orderbook endpoint returns list",
        assert_fn=_assert_orderbook,
    ),
    RegressionCase(
        id="upstox.search",
        capability="search",
        tier="off_market_safe",
        segment="NSE",
        description="Instrument search returns RELIANCE",
        assert_fn=_assert_search,
    ),
    RegressionCase(
        id="upstox.connection_status",
        capability="observability",
        tier="off_market_safe",
        segment="ACCOUNT",
        description="Connection status dict is available",
        assert_fn=_assert_connection_status,
        severity="P1",
    ),
    RegressionCase(
        id="upstox.portfolio_stream_capability",
        capability="portfolio_stream",
        tier="off_market_safe",
        segment="ACCOUNT",
        description="PORTFOLIO_STREAM capability targets portfolio_stream adapter",
        assert_fn=_assert_portfolio_stream_capability,
        severity="P0",
        tags=("regression_fix",),
    ),
    RegressionCase(
        id="upstox.subscribe_normalize",
        capability="ltp_stream",
        tier="off_market_safe",
        segment="NSE",
        description="DataProvider subscribe normalizes raw ticks to QuoteSnapshot",
        assert_fn=_assert_subscribe_normalizes_ticks,
        severity="P0",
        tags=("regression_fix",),
    ),
)

MARKET_HOURS_CASES: tuple[RegressionCase, ...] = (
    RegressionCase(
        id="upstox.nse.depth",
        capability="depth",
        tier="market_hours",
        segment="NSE",
        description="NSE REST depth returns at least one side",
        assert_fn=_assert_depth,
    ),
    RegressionCase(
        id="upstox.nse.ltp_stream",
        capability="ltp_stream",
        tier="market_hours",
        segment="NSE",
        description="LTP stream receives ticks during market hours",
        assert_fn=_assert_ltp_stream,
    ),
)

UPSTOX_REGRESSION_CASES: tuple[RegressionCase, ...] = OFF_MARKET_CASES + MARKET_HOURS_CASES
