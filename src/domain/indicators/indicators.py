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

    def macd(
        self, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> dict[str, list[float | None]]:
        return MACD(fast, slow, signal).calculate(self._closes())
