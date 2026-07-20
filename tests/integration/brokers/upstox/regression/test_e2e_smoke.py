"""End-to-end smoke tests for Upstox broker REST + streaming paths."""

from __future__ import annotations

import time

import pytest

from tests.market_hours import require_market_hours

pytestmark = [pytest.mark.upstox, pytest.mark.regression]

NSE_EQUITY = [("RELIANCE", "NSE"), ("TCS", "NSE")]


@pytest.mark.off_market_safe
class TestOffMarketSmoke:
    @pytest.mark.parametrize("symbol,exchange", NSE_EQUITY, ids=lambda x: x if isinstance(x, str) else "")
    def test_ltp(self, live_gateway, symbol, exchange):
        from decimal import Decimal

        ltp = live_gateway.ltp(symbol, exchange)
        assert isinstance(ltp, Decimal)
        assert ltp > 0
        time.sleep(1.0)

    @pytest.mark.parametrize("symbol,exchange", NSE_EQUITY[:1])
    def test_quote(self, live_gateway, symbol, exchange):
        q = live_gateway.quote(symbol, exchange)
        assert q.ltp > 0

    def test_portfolio_funds(self, live_gateway):
        bal = live_gateway.funds()
        assert bal is not None

    def test_history_daily(self, live_gateway):
        df = live_gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        assert df is not None and len(df) > 0


@pytest.mark.market_hours
@require_market_hours()
class TestMarketHoursSmoke:
    def test_ltp_stream(self, live_gateway):
        import contextlib
        import threading

        received = threading.Event()
        ticks: list[object] = []

        def on_tick(q):
            ticks.append(q)
            received.set()

        feed = live_gateway.stream("RELIANCE", "NSE", mode="LTP", on_tick=on_tick)
        try:
            got = received.wait(timeout=15)
            assert got and len(ticks) > 0
        finally:
            with contextlib.suppress(Exception):
                feed.disconnect()
