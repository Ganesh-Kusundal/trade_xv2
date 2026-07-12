"""Lightweight technical-indicator accessor over a HistoricalSeries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.candles.historical import HistoricalSeries


class SeriesIndicators:
    """Lightweight technical-indicator accessor over a :class:`HistoricalSeries`.

    All methods return a pandas ``Series`` indexed by the series' ``event_time``,
    suitable for plotting or further arithmetic. Pure-function: no state is
    mutated on the underlying series.
    """

    def __init__(self, series: HistoricalSeries) -> None:
        self._series = series

    def _close_series(self):
        import pandas as pd

        idx = [b.event_time for b in self._series.bars]
        vals = [float(b.close) for b in self._series.bars]
        return pd.Series(vals, index=pd.DatetimeIndex(idx, tz="UTC"), name="close")

    def sma(self, period: int) -> pd.Series:  # noqa: F821
        """Simple moving average of close over ``period`` bars."""
        s = self._close_series()
        return s.rolling(window=period, min_periods=period).mean().rename(f"sma_{period}")

    def ema(self, period: int) -> pd.Series:  # noqa: F821
        """Exponential moving average of close over ``period`` bars."""
        s = self._close_series()
        return s.ewm(span=period, adjust=False).mean().rename(f"ema_{period}")

    def rsi(self, period: int = 14) -> pd.Series:  # noqa: F821
        """Relative Strength Index of close (Wilder-style smoothing)."""
        import pandas as pd

        s = self._close_series()
        delta = s.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return rsi.rename(f"rsi_{period}")

    def patterns(self) -> pd.DataFrame:  # noqa: F821
        """Candlestick + swing pattern columns for this series."""
        import pandas as pd

        from domain.indicators.patterns import CandlestickPatterns

        idx = [b.event_time for b in self._series.bars]
        df = pd.DataFrame({
            "open": [float(b.open) for b in self._series.bars],
            "high": [float(b.high) for b in self._series.bars],
            "low": [float(b.low) for b in self._series.bars],
            "close": [float(b.close) for b in self._series.bars],
            "volume": [float(b.volume) for b in self._series.bars],
        })
        out = CandlestickPatterns().compute(df)
        out.index = pd.DatetimeIndex(idx, tz="UTC")
        return out
