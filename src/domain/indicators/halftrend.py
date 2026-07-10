"""HalfTrend indicator — trend-following indicator using ATR.

HalfTrend is a trend-following indicator that:
1. Uses ATR to determine trend direction
2. Provides clear BUY/SELL signals on trend changes
3. Acts as dynamic support/resistance

The indicator plots a line that follows price with an ATR offset.
When price crosses above the line + offset → BUY
When price crosses below the line - offset → SELL

Based on the TradingView HalfTrend indicator by everget.

Usage:
    from analytics.indicators.halftrend import HalfTrend
    ht = HalfTrend(period=10, atr_period=10, deviation=1.0)
    result = ht.compute(df)
    # Columns added: halftrend, halftrend_direction, halftrend_signal
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
# ponytail: lazy import — domain purity forbids top-level pandas
# import pandas as pd  (imported inside each method)


@dataclass(frozen=True)
class HalfTrend:
    """HalfTrend indicator.

    Parameters
    ----------
    period : int
        Lookback period for the highest high / lowest low (default 10).
    atr_period : int
        ATR period for volatility offset (default 10).
    deviation : float
        ATR multiplier for the band offset (default 1.0).
    cooldown : int
        Minimum bars between signals to prevent overtrading (default 50).
    name : str
        Feature name for pipeline compatibility.
    """

    period: int = 10
    atr_period: int = 10
    deviation: float = 1.0
    cooldown: int = 50
    name: str = "halftrend"

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        import pandas as pd

        """Compute HalfTrend and add columns to DataFrame.

        Adds:
        - halftrend: the indicator line
        - halftrend_direction: 1 = uptrend, -1 = downtrend, 0 = undefined
        - halftrend_signal: BUY, SELL, or HOLD
        """
        if df.empty or len(df) < max(self.period, self.atr_period) + 2:
            df = df.copy()
            df["halftrend"] = np.nan
            df["halftrend_direction"] = 0
            df["halftrend_signal"] = "HOLD"
            return df

        df = df.copy()
        high = df["high"].values.astype(float)
        low = df["low"].values.astype(float)
        close = df["close"].values.astype(float)

        n = len(df)

        # Compute ATR
        atr = self._compute_atr(high, low, close, self.atr_period)

        # HalfTrend core logic
        ht = np.full(n, np.nan)
        direction = np.zeros(n)
        next_high = np.full(n, np.nan)
        next_low = np.full(n, np.nan)

        # Initialize
        start = max(self.period, self.atr_period)
        direction[start - 1] = 1  # Start in uptrend

        # Initialize bands based on first bar
        next_high[start - 1] = high[start - 1] - atr[start - 1] * self.deviation
        next_low[start - 1] = low[start - 1] + atr[start - 1] * self.deviation
        ht[start - 1] = next_low[start - 1]

        for i in range(start, n):
            atr_dev = atr[i] * self.deviation

            if direction[i - 1] == 1:  # Was uptrend
                # Update upper band (trailing stop for uptrend)
                new_high = high[i] - atr_dev
                next_high[i] = (
                    max(next_high[i - 1], new_high) if not np.isnan(next_high[i - 1]) else new_high
                )

                # Lower band follows price up
                new_low = low[i] + atr_dev
                if not np.isnan(next_low[i - 1]):
                    next_low[i] = next_low[i - 1] + min(new_low - next_low[i - 1], atr_dev)
                else:
                    next_low[i] = new_low

                # Trend line is the lower band in uptrend
                ht[i] = next_low[i]

                # Check for reversal to downtrend
                if close[i] < next_low[i]:
                    direction[i] = -1
                    # Set upper band for new downtrend
                    next_high[i] = high[i] - atr_dev
                    next_low[i] = next_low[i - 1] if not np.isnan(next_low[i - 1]) else new_low
                else:
                    direction[i] = 1

            else:  # Was downtrend
                # Update lower band (trailing stop for downtrend)
                new_low = low[i] + atr_dev
                next_low[i] = (
                    min(next_low[i - 1], new_low) if not np.isnan(next_low[i - 1]) else new_low
                )

                # Upper band follows price down
                new_high = high[i] - atr_dev
                if not np.isnan(next_high[i - 1]):
                    next_high[i] = next_high[i - 1] - min(next_high[i - 1] - new_high, atr_dev)
                else:
                    next_high[i] = new_high

                # Trend line is the upper band in downtrend
                ht[i] = next_high[i]

                # Check for reversal to uptrend
                if close[i] > next_high[i]:
                    direction[i] = 1
                    # Set lower band for new uptrend
                    next_low[i] = low[i] + atr_dev
                    next_high[i] = next_high[i - 1] if not np.isnan(next_high[i - 1]) else new_high
                else:
                    direction[i] = -1

        # Generate signals with cooldown
        signals = np.full(n, "HOLD", dtype="U10")
        last_signal_idx = -self.cooldown - 1  # Allow first signal immediately
        for i in range(start + 1, n):
            if i - last_signal_idx < self.cooldown:
                continue  # In cooldown period
            if direction[i] == 1 and direction[i - 1] != 1:
                signals[i] = "BUY"
                last_signal_idx = i
            elif direction[i] == -1 and direction[i - 1] != -1:
                signals[i] = "SELL"
                last_signal_idx = i

        df["halftrend"] = ht
        df["halftrend_direction"] = direction.astype(int)
        df["halftrend_signal"] = signals

        return df

    def _compute_atr(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
    ) -> np.ndarray:
        """Compute Average True Range."""
        n = len(high)
        tr = np.zeros(n)
        tr[0] = high[0] - low[0]

        for i in range(1, n):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr[i] = max(hl, hc, lc)

        # Smoothed ATR (Wilder's method)
        atr = np.zeros(n)
        atr[:period] = np.nan
        atr[period - 1] = np.mean(tr[:period])

        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        return atr
