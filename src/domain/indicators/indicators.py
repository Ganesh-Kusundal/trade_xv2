from plugins.indicators.rsi import RSI
from plugins.indicators.atr import ATR
from plugins.indicators.vwap import VWAP
from plugins.indicators.macd import MACD


class Indicators:
    def __init__(self, instrument):
        self._inst = instrument

    def rsi(self, period: int = 14):
        df = self._inst.history()
        return RSI(period).calculate(df)

    def atr(self, period: int = 14):
        df = self._inst.history()
        return ATR(period).calculate(df)

    def vwap(self):
        df = self._inst.history()
        return VWAP().calculate(df)

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        df = self._inst.history()
        return MACD(fast, slow, signal).calculate(df)
