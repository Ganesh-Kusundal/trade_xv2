"""RSI — pure domain math (no pandas dependency).

Canonical RSI implementation for TradeXV2 (Wilder/EMA, SMA-seeded).

ponytail: Three RSI implementations coexist and are intentionally NOT merged
(RC-C): this module (Wilder), `datalake/analytics/features.py` (pandas EWM,
Wilder-family but different warm-up/`replace(0,nan)` handling), and
`analytics/views/features.py` (SQL simple moving average — materially
different values). No consumer reconciles across paths, so treat this module
as the reference. If you add an indicator that must match another path, align
to this math rather than assuming the others agree.
"""

from __future__ import annotations

from collections.abc import Sequence


class RSI:
    def __init__(self, period: int = 14) -> None:
        self.period = period

    def calculate(self, closes: Sequence[float]) -> list[float | None]:
        """Wilder-style RSI on a close series. Leading values are ``None``."""
        n = len(closes)
        if n == 0:
            return []
        out: list[float | None] = [None] * n
        if n < self.period + 1:
            return out

        gains = [0.0] * n
        losses = [0.0] * n
        for i in range(1, n):
            delta = float(closes[i]) - float(closes[i - 1])
            gains[i] = max(delta, 0.0)
            losses[i] = max(-delta, 0.0)

        avg_gain = sum(gains[1 : self.period + 1]) / self.period
        avg_loss = sum(losses[1 : self.period + 1]) / self.period
        alpha = 1.0 / self.period

        def _rsi(ag: float, al: float) -> float:
            if al == 0.0:
                return 100.0 if ag > 0 else 50.0
            rs = ag / al
            return 100.0 - 100.0 / (1.0 + rs)

        out[self.period] = _rsi(avg_gain, avg_loss)
        for i in range(self.period + 1, n):
            avg_gain = (1.0 - alpha) * avg_gain + alpha * gains[i]
            avg_loss = (1.0 - alpha) * avg_loss + alpha * losses[i]
            out[i] = _rsi(avg_gain, avg_loss)
        return out

    def calculate_frame(self, df):  # pragma: no cover - export adapter
        """Lazy pandas export adapter for notebook/analytics callers."""
        import pandas as pd

        closes = df["close"].astype(float).tolist()
        values = self.calculate(closes)
        return pd.Series(values, index=df.index, name="rsi")
