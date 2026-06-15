"""Tests for PaperTradingEngine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import (
    OrderSide,
    OrderStatus,
    PaperConfig,
    PaperOrder,
    PaperPosition,
    PaperResult,
    PaperSession,
    PaperTrade,
    PositionSide,
)
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.models import Bar


def _make_ohlcv(n=100, start_price=100.0, symbol="TEST"):
    import numpy as np
    np.random.seed(42)
    dates = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(n)]
    close = start_price + np.cumsum(np.random.randn(n) * 2)
    high = close + abs(np.random.randn(n))
    low = close - abs(np.random.randn(n))
    open_ = close + np.random.randn(n) * 0.5
    volume = np.random.randint(10000, 100000, n).astype(float)
    return pd.DataFrame({
        "timestamp": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume, "symbol": symbol,
    })


def _make_multi(n=100, symbols=None):
    if symbols is None:
        symbols = ["RELIANCE", "TCS", "HDFC"]
    return pd.concat([_make_ohlcv(n, symbol=s) for s in symbols], ignore_index=True)


def _pipeline():
    from analytics.pipeline import RSI, ATR, SMA
    return FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))


# --- Models ---

class TestPaperConfig:
    def test_defaults(self):
        c = PaperConfig()
        assert c.initial_capital == 100_000.0
        assert c.max_positions == 5

    def test_custom(self):
        c = PaperConfig(initial_capital=50_000, max_positions=10)
        assert c.initial_capital == 50_000
        assert c.max_positions == 10


class TestPaperOrder:
    def test_order_value(self):
        o = PaperOrder(order_id="P-1", symbol="T", side=OrderSide.BUY,
                       quantity=100, price=50.0, order_time=datetime.now(timezone.utc))
        assert o.order_value == 5000.0
        assert o.status == OrderStatus.PENDING

    def test_fill_value(self):
        o = PaperOrder(order_id="P-2", symbol="T", side=OrderSide.BUY,
                       quantity=100, price=50.0, order_time=datetime.now(timezone.utc),
                       fill_price=50.5, status=OrderStatus.FILLED)
        assert o.fill_value == 5050.0


class TestPaperPosition:
    def test_long_pnl(self):
        p = PaperPosition(symbol="T", side=PositionSide.LONG, entry_price=100.0,
                          quantity=100, entry_time=datetime.now(timezone.utc), current_price=105.0)
        assert p.unrealized_pnl == 500.0
        assert abs(p.unrealized_pnl_pct - 5.0) < 0.01

    def test_short_pnl(self):
        p = PaperPosition(symbol="T", side=PositionSide.SHORT, entry_price=100.0,
                          quantity=100, entry_time=datetime.now(timezone.utc), current_price=95.0)
        assert p.unrealized_pnl == 500.0

    def test_notional(self):
        p = PaperPosition(symbol="T", side=PositionSide.LONG, entry_price=50.0,
                          quantity=200, entry_time=datetime.now(timezone.utc))
        assert p.notional == 10_000.0

    def test_update_price(self):
        p = PaperPosition(symbol="T", side=PositionSide.LONG, entry_price=100.0,
                          quantity=100, entry_time=datetime.now(timezone.utc), current_price=100.0)
        p.update_price(110.0)
        assert p.current_price == 110.0
        assert p.unrealized_pnl == 1000.0


class TestPaperSession:
    def test_empty(self):
        s = PaperSession(capital=100_000)
        assert s.total_equity == 100_000
        assert s.position_count == 0
        assert s.win_rate == 0.0

    def test_with_positions(self):
        s = PaperSession(capital=80_000)
        s.positions["T"] = PaperPosition(symbol="T", side=PositionSide.LONG,
            entry_price=100.0, quantity=100, entry_time=datetime.now(timezone.utc), current_price=110.0)
        assert s.total_equity == 81_000
        assert s.position_count == 1
        assert s.total_unrealized_pnl == 1000.0


class TestPaperTrade:
    def test_winning_trade(self):
        t = PaperTrade(symbol="T", side=OrderSide.BUY, entry_price=100.0, exit_price=110.0,
                       quantity=100, entry_time=datetime.now(timezone.utc),
                       exit_time=datetime.now(timezone.utc), pnl=1000.0, pnl_pct=10.0,
                       commission=3.3, slippage_cost=1.1, strategy="mom")
        assert t.pnl == 1000.0
        assert t.pnl_pct == 10.0


# --- Engine single ---

class TestEngineSingle:
    def test_basic_run(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=20)).run(_make_ohlcv(100), symbol="T")
        assert isinstance(r, PaperResult)
        assert r.bars_processed == 100
        assert r.config.initial_capital == 100_000

    def test_empty_data(self):
        r = PaperTradingEngine(_pipeline()).run(pd.DataFrame(), symbol="T")
        assert r.bars_processed == 0
        assert r.final_equity == 0.0

    def test_no_timestamp_raises(self):
        with pytest.raises(ValueError, match="timestamp"):
            PaperTradingEngine(_pipeline()).run(pd.DataFrame({"close": [100]}))

    def test_no_signals_preserves_capital(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(initial_capital=50_000, warmup_bars=50)).run(_make_ohlcv(100), symbol="T")
        assert r.final_equity == 50_000
        assert r.session.position_count == 0

    def test_equity_curve(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=20)).run(_make_ohlcv(100), symbol="T")
        assert len(r.session.equity_curve) > 0
        assert r.session.equity_curve[0][1] == 100_000

    def test_peak_equity(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=20)).run(_make_ohlcv(100), symbol="T")
        assert r.session.peak_equity >= 100_000


# --- Engine multi ---

class TestEngineMulti:
    def test_multi_run(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=20)).run(_make_multi(100, ["R", "T"]))
        assert r.bars_processed > 0

    def test_position_limit(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=5, max_positions=2)).run(_make_multi(100, ["A", "B", "C", "D"]))
        assert r.session.position_count <= 2


# --- on_bar ---

class TestOnBar:
    def test_on_bar(self):
        engine = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=2))
        session = PaperSession(capital=100_000)
        session.peak_equity = 100_000
        for i in range(5):
            bar = Bar(symbol="T", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                      open=100.0+i, high=101.0+i, low=99.0+i, close=100.5+i, volume=10000)
            engine.on_bar(bar, session)
        assert session.bar_count == 5
        assert len(session.equity_curve) > 0

    def test_warmup_no_signals(self):
        engine = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=10))
        session = PaperSession(capital=100_000)
        session.peak_equity = 100_000
        for i in range(5):
            bar = Bar(symbol="T", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                      open=100.0, high=101.0, low=99.0, close=100.0, volume=10000)
            engine.on_bar(bar, session)
        assert len(session.positions) == 0


# --- Position management ---

class TestPositionManagement:
    def test_stop_loss_no_crash(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=5, stop_loss_pct=1.0, slippage_pct=0.0)).run(_make_ohlcv(100), symbol="T")
        assert isinstance(r, PaperResult)

    def test_position_limit_respected(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=5, max_positions=2)).run(_make_multi(100, ["A", "B", "C", "D", "E", "F"]))
        assert r.session.position_count <= 2

    def test_commission_tracked(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=10, commission_pct=0.001)).run(_make_ohlcv(100), symbol="T")
        if r.session.trades:
            assert r.session.total_commission > 0


# --- Result summary ---

class TestPaperResult:
    def test_summary_keys(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=20)).run(_make_ohlcv(100), symbol="T")
        s = r.summary
        for key in ["bars_processed", "signals_generated", "total_trades", "open_positions",
                     "win_rate", "final_equity", "total_return_pct", "total_pnl",
                     "commission", "max_drawdown_pct", "sharpe_ratio", "available_capital"]:
            assert key in s

    def test_total_return_pct(self):
        r = PaperTradingEngine(_pipeline(), config=PaperConfig(warmup_bars=20)).run(_make_ohlcv(100), symbol="T")
        assert isinstance(r.total_return_pct, float)
