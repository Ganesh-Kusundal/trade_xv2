"""ATR — pure domain math (no pandas dependency)."""

from __future__ import annotations

from collections.abc import Sequence


class ATR:
    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate(
        self,
        highs: Sequence[float],
        lows: Sequence[float],
        closes: Sequence[float],
    ) -> list[float | None]:
        n = len(closes)
        if not (len(highs) == len(lows) == n):
            raise ValueError("highs, lows, closes must have equal length")
        out: list[float | None] = [None] * n
        if n < 2:
            return out

        trs: list[float] = [0.0] * n
        trs[0] = float(highs[0]) - float(lows[0])
        for i in range(1, n):
            h, l, prev_c = float(highs[i]), float(lows[i]), float(closes[i - 1])
            trs[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))

        if n <= self.period:
            return out

        atr = sum(trs[1 : self.period + 1]) / self.period
        out[self.period] = atr
        alpha = 1.0 / self.period
        for i in range(self.period + 1, n):
            atr = (1.0 - alpha) * atr + alpha * trs[i]
            out[i] = atr
        return out

    def calculate_frame(self, df):  # pragma: no cover - export adapter
        import pandas as pd

        values = self.calculate(
            df["high"].astype(float).tolist(),
            df["low"].astype(float).tolist(),
            df["close"].astype(float).tolist(),
        )
        return pd.Series(values, index=df.index, name="atr")
