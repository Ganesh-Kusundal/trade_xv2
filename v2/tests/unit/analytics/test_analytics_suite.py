"""Known-input checks for application.analytics.suite (E2)."""

from __future__ import annotations

import math
from decimal import Decimal

from application.analytics.suite.fundamentals import pe_ratio
from application.analytics.suite.futures import basis
from application.analytics.suite.indicators import ema, rsi, sma
from application.analytics.suite.market_breadth import advance_decline
from application.analytics.suite.options import black_scholes_call, intrinsic_call
from application.analytics.suite.orderflow import imbalance
from application.analytics.suite.probability import win_rate
from application.analytics.suite.ranking import rank_by_return
from application.analytics.suite.reports import max_drawdown, sharpe
from application.analytics.suite.scanner import momentum_scan
from application.analytics.suite.sector import sector_strength
from application.analytics.suite.volatility import realized_vol
from application.analytics.suite.volume_profile import poc
from application.analytics.suite.walk_forward import split_windows


def test_sma():
    assert sma([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [2.0, 3.0, 4.0]


def test_ema():
    # alpha=0.5, seed SMA(1,2,3)=2 → 3, 4
    assert ema([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [2.0, 3.0, 4.0]


def test_rsi_all_gains_is_100():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
    assert rsi(prices, 5)[-1] == 100.0


def test_momentum_scan_ranks_by_return():
    bars = {"A": [100.0, 110.0], "B": [100.0, 105.0], "C": [100.0, 90.0]}
    ranked = momentum_scan(bars)
    assert [r.symbol for r in ranked] == ["A", "B", "C"]
    assert abs(ranked[0].momentum - 0.1) < 1e-12


def test_rank_by_return():
    assert rank_by_return({"X": 0.05, "Y": 0.2, "Z": -0.1}) == ["Y", "X", "Z"]


def test_sector_strength():
    ranked = sector_strength({"Tech": 0.1, "Energy": -0.05, "Banks": 0.02})
    assert ranked[0] == ("Tech", 0.1)
    assert ranked[-1] == ("Energy", -0.05)


def test_options_intrinsic_and_bs():
    assert intrinsic_call(110.0, 100.0) == 10.0
    assert intrinsic_call(90.0, 100.0) == 0.0
    # ATM r=0 σ=0.2 T=1 → ≈ 7.965567
    price = black_scholes_call(100.0, 100.0, 1.0, 0.0, 0.2)
    assert abs(price - 7.965567) < 1e-4


def test_futures_basis():
    assert basis(105.0, 100.0) == 5.0
    assert basis(Decimal("105"), Decimal("100")) == Decimal("5")


def test_realized_vol():
    # two equal +10% then -10%/1.1 log returns → known annualized
    prices = [100.0, 110.0, 100.0]
    vol = realized_vol(prices, periods_per_year=252)
    r1 = math.log(1.1)
    r2 = math.log(100 / 110)
    mean = (r1 + r2) / 2
    var = ((r1 - mean) ** 2 + (r2 - mean) ** 2) / 1  # sample std, ddof=1
    expected = math.sqrt(var) * math.sqrt(252)
    assert abs(vol - expected) < 1e-9


def test_orderflow_imbalance():
    assert imbalance(60.0, 40.0) == 0.2
    assert imbalance(0.0, 0.0) == 0.0


def test_advance_decline():
    assert advance_decline([1.0, -0.5, 0.2, -0.1, 0.0]) == (2, 2, 1.0)


def test_volume_profile_poc():
    assert poc({100.0: 10.0, 101.0: 50.0, 102.0: 20.0}) == 101.0


def test_win_rate():
    assert win_rate([1.0, -1.0, 2.0, 0.5]) == 0.75
    assert win_rate([]) == 0.0


def test_pe_ratio():
    assert pe_ratio(100.0, 5.0) == 20.0


def test_reports_sharpe_and_max_drawdown():
    equity = [100.0, 110.0, 105.0, 120.0]
    # returns: 0.1, -0.04545..., 0.142857...
    s = sharpe(equity, risk_free=0.0, periods_per_year=252)
    assert s > 0
    assert max_drawdown([100.0, 120.0, 90.0, 110.0]) == 0.25


def test_walk_forward_windows():
    assert split_windows(10, train=4, test=2) == [(0, 4, 4, 6), (2, 6, 6, 8), (4, 8, 8, 10)]
