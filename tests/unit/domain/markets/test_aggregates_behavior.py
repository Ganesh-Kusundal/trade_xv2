"""Tests for domain aggregates: Exchange (canonical), Order/Position/Portfolio (superseded).

The OrderLifecycle / PositionLifecycle / Portfolio tests that previously lived
here tested the anemic ``domain.trading`` dataclasses, which have been deleted
in Phase 4. Their behavior is now tested via:
  - ``tests/unit/domain/test_instrument.py`` (Instrument/OptionChain/subscribe)
  - ``tests/unit/domain/test_execution.py`` (Execution aggregate)
  - ``tests/unit/domain/test_portfolio.py`` (Portfolio PnL/exposure/concentration)
  - ``tests/unit/domain/test_risk_policy.py`` (risk policies)
"""

from __future__ import annotations

from datetime import date, time

from domain.market.exchange import Exchange, TradingSession


class TestExchange:
    def test_is_trading_day_normal(self):
        ex = Exchange(name="NSE", timezone="Asia/Kolkata")
        assert ex.is_trading_day(date(2026, 7, 10)) is True

    def test_is_trading_day_holiday(self):
        holidays = frozenset({date(2026, 8, 15), date(2026, 10, 2)})
        ex = Exchange(name="NSE", timezone="Asia/Kolkata", holidays=holidays)
        assert ex.is_trading_day(date(2026, 8, 15)) is False
        assert ex.is_trading_day(date(2026, 8, 16)) is True

    def test_frozen(self):
        ex = Exchange(name="NSE", timezone="Asia/Kolkata")
        assert ex.__dataclass_params__.frozen

    def test_repr(self):
        ex = Exchange(name="NSE", timezone="Asia/Kolkata")
        r = repr(ex)
        assert "NSE" in r
        assert "Asia/Kolkata" in r

    def test_sessions_and_products(self):
        session = TradingSession(name="regular", open_time=time(9, 15), close_time=time(15, 30))
        ex = Exchange(
            name="NSE",
            timezone="Asia/Kolkata",
            sessions=(session,),
            products=frozenset({"EQ", "FO"}),
        )
        assert len(ex.sessions) == 1
        assert "EQ" in ex.products
