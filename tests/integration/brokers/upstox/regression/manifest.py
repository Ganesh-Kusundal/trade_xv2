"""Upstox regression suite manifest — P0 capability coverage."""

from __future__ import annotations

from brokers.upstox.wire import UpstoxBrokerGateway
from tests.support.brokers.regression_manifest import RegressionCase


def _assert_nse_quote(gw: UpstoxBrokerGateway) -> None:
    q = gw.quote("RELIANCE", "NSE")
    assert q.ltp > 0


def _assert_nse_ltp(gw: UpstoxBrokerGateway) -> None:
    ltp = gw.ltp("RELIANCE", "NSE")
    assert ltp > 0


def _assert_nse_history(gw: UpstoxBrokerGateway) -> None:
    df = gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
    assert df is not None and len(df) > 0
    for col in ("open", "high", "low", "close", "volume"):
        assert col in getattr(df, "columns", ()), f"Missing column: {col}"


def _assert_funds(gw: UpstoxBrokerGateway) -> None:
    bal = gw.funds()
    assert bal is not None


def _assert_positions(gw: UpstoxBrokerGateway) -> None:
    assert isinstance(gw.positions(), list)


def _assert_holdings(gw: UpstoxBrokerGateway) -> None:
    assert isinstance(gw.holdings(), list)


def _assert_orderbook(gw: UpstoxBrokerGateway) -> None:
    book = gw.get_orderbook() if hasattr(gw, "get_orderbook") else gw.orderbook()
    assert isinstance(book, list)


def _assert_search(gw: UpstoxBrokerGateway) -> None:
    results = gw.search("RELIANCE")
    assert isinstance(results, list)
    assert len(results) >= 1


def _assert_depth(gw: UpstoxBrokerGateway) -> None:
    depth = gw.depth("RELIANCE", "NSE")
    assert depth is not None
    assert len(depth.bids) >= 1 or len(depth.asks) >= 1


def _assert_option_chain(gw: UpstoxBrokerGateway) -> None:
    chain = gw.option_chain("NIFTY", "NSE")
    assert chain is not None


def _assert_connection_status(gw: UpstoxBrokerGateway) -> None:
    if not hasattr(gw, "get_connection_status"):
        return
    status = gw.get_connection_status()
    assert isinstance(status, dict)


UPSTOX_REGRESSION_CASES: tuple[RegressionCase, ...] = (
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
        id="upstox.nse.depth",
        capability="depth",
        tier="market_hours",
        segment="NSE",
        description="NSE REST depth returns at least one side",
        assert_fn=_assert_depth,
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
)
