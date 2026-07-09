"""VWAP — pure domain math (no pandas dependency)."""

from __future__ import annotations

from collections.abc import Sequence


class VWAP:
    def calculate(
        self,
        closes: Sequence[float],
        volumes: Sequence[float],
        *,
        highs: Sequence[float] | None = None,
        lows: Sequence[float] | None = None,
    ) -> list[float | None]:
        """Cumulative VWAP. Uses typical price (H+L+C)/3 when high/low given."""
        n = len(closes)
        if len(volumes) != n:
            raise ValueError("closes and volumes must have equal length")
        out: list[float | None] = [None] * n
        cum_pv = 0.0
        cum_v = 0.0
        for i in range(n):
            c = float(closes[i])
            if highs is not None and lows is not None:
                price = (float(highs[i]) + float(lows[i]) + c) / 3.0
            else:
                price = c
            v = float(volumes[i])
            cum_pv += price * v
            cum_v += v
            out[i] = (cum_pv / cum_v) if cum_v else None
        return out

    def calculate_frame(self, df):  # pragma: no cover - export adapter
        import pandas as pd

        values = self.calculate(
            df["close"].astype(float).tolist(),
            df["volume"].astype(float).tolist(),
            highs=df["high"].astype(float).tolist() if "high" in df else None,
            lows=df["low"].astype(float).tolist() if "low" in df else None,
        )
        return pd.Series(values, index=df.index, name="vwap")
