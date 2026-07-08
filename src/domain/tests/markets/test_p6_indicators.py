import pandas as pd

from plugins.indicators.rsi import RSI
from plugins.indicators.atr import ATR
from plugins.indicators.vwap import VWAP
from plugins.indicators.macd import MACD


def _make_df():
    return pd.DataFrame(
        {
            "open": [44, 44.3, 44.1, 43.6, 44.3],
            "high": [44.5, 44.5, 44.4, 44.1, 44.8],
            "low": [43.9, 44.0, 43.5, 43.4, 44.0],
            "close": [44.2, 44.1, 43.7, 44.0, 44.7],
            "volume": [1000, 1200, 900, 1100, 1300],
        }
    )


def test_rsi_range():
    df = _make_df()
    rsi = RSI(14).calculate(df)
    valid = rsi.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_atr_positive():
    df = _make_df()
    atr = ATR(14).calculate(df)
    valid = atr.dropna()
    assert (valid > 0).all()


def test_vwap_cumulative():
    df = _make_df()
    vwap = VWAP().calculate(df)
    expected = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
    pd.testing.assert_series_equal(vwap, expected)


def test_macd_columns():
    df = _make_df()
    result = MACD().calculate(df)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["macd", "signal", "histogram"]
    assert len(result) == len(df)
