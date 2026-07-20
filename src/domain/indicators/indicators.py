"""Indicators facade bound to an Instrument (pure domain)."""

from __future__ import annotations

from domain.indicators.atr import ATR
from domain.indicators.macd import MACD
from domain.indicators.rsi import RSI
from domain.indicators.vwap import VWAP


class Indicators:
    def __init__(self, instrument) -> None:
        self._inst = instrument

    def _closes(self) -> list[float]:
        series = self._inst.history()
        return [float(b.close) for b in series.bars]

    def _ohlcv(self) -> tuple[list[float], list[float], list[float], list[float]]:
        series = self._inst.history()
        highs = [float(b.high) for b in series.bars]
        lows = [float(b.low) for b in series.bars]
        closes = [float(b.close) for b in series.bars]
        volumes = [float(b.volume) for b in series.bars]
        return highs, lows, closes, volumes

    def rsi(self, period: int = 14) -> list[float | None]:
        return RSI(period).calculate(self._closes())

    def atr(self, period: int = 14) -> list[float | None]:
        highs, lows, closes, _ = self._ohlcv()
        return ATR(period).calculate(highs, lows, closes)

    def vwap(self) -> list[float | None]:
        highs, lows, closes, volumes = self._ohlcv()
        return VWAP().calculate(closes, volumes, highs=highs, lows=lows)

    def patterns(self) -> dict[str, list[bool | str | None]]:
        """Detect candlestick + swing patterns over the instrument's history.

        Returns a mapping of pattern-column name -> per-bar value (bool for
        pattern flags, str for ``cdl_direction``). Mirrors ``macd()`` in shape.
        """
        from domain.indicators.patterns import CandlestickPatterns

        bars = self._inst.history().bars
        import pandas as pd

        df = pd.DataFrame(
            {
                "open": [float(b.open) for b in bars],
                "high": [float(b.high) for b in bars],
                "low": [float(b.low) for b in bars],
                "close": [float(b.close) for b in bars],
                "volume": [float(b.volume) for b in bars],
            }
        )
        out = CandlestickPatterns().compute(df)
        return {
            col: out[col].tolist()
            for col in out.columns
            if col not in ("open", "high", "low", "close", "volume")
        }

    def macd(
        self, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> dict[str, list[float | None]]:
        return MACD(fast, slow, signal).calculate(self._closes())
