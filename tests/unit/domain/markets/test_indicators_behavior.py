"""Domain indicators — pure series math (no pandas required)."""

from domain.indicators.atr import ATR
from domain.indicators.macd import MACD
from domain.indicators.rsi import RSI
from domain.indicators.vwap import VWAP


def _ohlcv():
    opens = [44, 44.3, 44.1, 43.6, 44.3]
    highs = [44.5, 44.5, 44.4, 44.1, 44.8]
    lows = [43.9, 44.0, 43.5, 43.4, 44.0]
    closes = [44.2, 44.1, 43.7, 44.0, 44.7]
    volumes = [1000, 1200, 900, 1100, 1300]
    return opens, highs, lows, closes, volumes


def test_rsi_range():
    *_, closes, _ = _ohlcv()
    # longer series for period=14
    closes = closes * 5
    rsi = RSI(14).calculate(closes)
    valid = [v for v in rsi if v is not None]
    assert valid
    assert all(0 <= v <= 100 for v in valid)


def test_atr_positive():
    _, highs, lows, closes, _ = _ohlcv()
    highs, lows, closes = highs * 5, lows * 5, closes * 5
    atr = ATR(14).calculate(highs, lows, closes)
    valid = [v for v in atr if v is not None]
    assert valid
    assert all(v > 0 for v in valid)


def test_vwap_cumulative():
    _, highs, lows, closes, volumes = _ohlcv()
    vwap = VWAP().calculate(closes, volumes, highs=highs, lows=lows)
    assert len(vwap) == len(closes)
    assert all(v is not None and v > 0 for v in vwap)
    # last vwap is cumulative typical*vol / cum vol
    typical = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes, strict=False)]
    cum_pv = sum(t * v for t, v in zip(typical, volumes, strict=False))
    cum_v = sum(volumes)
    assert abs(vwap[-1] - cum_pv / cum_v) < 1e-9


def test_macd_keys():
    *_, closes, _ = _ohlcv()
    closes = closes * 10
    result = MACD().calculate(closes)
    assert set(result) == {"macd", "signal", "histogram"}
    assert len(result["macd"]) == len(closes)
