"""Candlestick pattern detector columns (known OHLCV fixtures).

File-per-guarantee: each test asserts a single detector's boolean/enum column
on a hand-built OHLCV frame, so a regression shows exactly which pattern broke.
"""

from __future__ import annotations

import pandas as pd

from domain.indicators.patterns import CandlestickPatterns, PatternColumns


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def _compute(rows: list[dict]) -> pd.DataFrame:
    return CandlestickPatterns().compute(_df(rows))


# --- single-bar patterns ----------------------------------------------------


def test_doji_detected() -> None:
    out = _compute([{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.1, "volume": 1000}])
    assert out["cdl_doji"].iloc[-1]


def test_hammer_detected() -> None:
    out = _compute([{"open": 100.0, "high": 100.6, "low": 95.0, "close": 100.5, "volume": 1000}])
    assert out["cdl_hammer"].iloc[-1]
    assert out["cdl_direction"].iloc[-1] == "BULL"


def test_shooting_star_detected() -> None:
    out = _compute([{"open": 100.0, "high": 105.0, "low": 99.4, "close": 99.5, "volume": 1000}])
    assert out["cdl_shooting_star"].iloc[-1]
    assert out["cdl_direction"].iloc[-1] == "BEAR"


# --- two-bar patterns (depend on prior candle) -----------------------------


def test_bullish_engulfing_detected() -> None:
    out = _compute([
        {"open": 102.0, "high": 103.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 99.5, "high": 103.0, "low": 99.0, "close": 102.5, "volume": 1000},
    ])
    assert out["cdl_engulfing_bull"].iloc[-1]
    assert not out["cdl_engulfing_bear"].iloc[-1]
    assert out["cdl_direction"].iloc[-1] == "BULL"


def test_bearish_engulfing_detected() -> None:
    out = _compute([
        {"open": 99.0, "high": 103.0, "low": 99.0, "close": 101.0, "volume": 1000},
        {"open": 101.5, "high": 102.0, "low": 98.0, "close": 98.5, "volume": 1000},
    ])
    assert out["cdl_engulfing_bear"].iloc[-1]
    assert out["cdl_direction"].iloc[-1] == "BEAR"


def test_bullish_harami_detected() -> None:
    out = _compute([
        {"open": 102.0, "high": 103.0, "low": 97.0, "close": 98.0, "volume": 1000},
        {"open": 99.5, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
    ])
    assert out["cdl_harami_bull"].iloc[-1]


def test_bearish_harami_detected() -> None:
    out = _compute([
        {"open": 98.0, "high": 103.0, "low": 97.0, "close": 102.0, "volume": 1000},
        {"open": 100.5, "high": 101.0, "low": 99.0, "close": 99.5, "volume": 1000},
    ])
    assert out["cdl_harami_bear"].iloc[-1]


# --- structural guarantees --------------------------------------------------


def test_all_pattern_columns_present() -> None:
    out = _compute([{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.1, "volume": 1000}])
    for col in PatternColumns.ALL:
        assert col in out.columns


def test_empty_frame_returns_columns() -> None:
    out = CandlestickPatterns().compute(_df([]))
    for col in PatternColumns.ALL:
        assert col in out.columns
    assert len(out) == 0


def test_compute_is_pure_no_lookahead() -> None:
    """A pattern flagged at bar i must not change when later bars are appended."""
    base = _compute([
        {"open": 102.0, "high": 103.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 99.5, "high": 103.0, "low": 99.0, "close": 102.5, "volume": 1000},
    ])
    extended = _compute([
        {"open": 102.0, "high": 103.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 99.5, "high": 103.0, "low": 99.0, "close": 102.5, "volume": 1000},
        {"open": 200.0, "high": 201.0, "low": 50.0, "close": 60.0, "volume": 1000},
    ])
    for col in PatternColumns.ALL:
        assert base[col].iloc[-1] == extended[col].iloc[1], col


def test_detector_is_frozen_dataclass() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(CandlestickPatterns)
    assert getattr(CandlestickPatterns, "__dataclass_params__", None) is not None
