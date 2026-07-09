"""MACD — pure domain math (no pandas dependency)."""

from __future__ import annotations

from collections.abc import Sequence


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    alpha = 2.0 / (period + 1)
    seed = sum(float(values[i]) for i in range(period)) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = alpha * float(values[i]) + (1.0 - alpha) * prev
        out[i] = prev
    return out


class MACD:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def calculate(self, closes: Sequence[float]) -> dict[str, list[float | None]]:
        fast_ema = _ema(closes, self.fast)
        slow_ema = _ema(closes, self.slow)
        n = len(closes)
        macd: list[float | None] = [None] * n
        for i in range(n):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                macd[i] = float(fast_ema[i]) - float(slow_ema[i])  # type: ignore[arg-type]

        # Signal EMA over available MACD values (treat None as skip in seed)
        signal_line: list[float | None] = [None] * n
        hist: list[float | None] = [None] * n
        # Build contiguous macd series from first non-None
        first = next((i for i, v in enumerate(macd) if v is not None), None)
        if first is not None:
            macd_vals = [float(v) if v is not None else 0.0 for v in macd]
            # Only meaningful after slow period; compute EMA on full series with Nones zeroed after first
            sig = _ema([float(m) if m is not None else 0.0 for m in macd], self.signal)
            for i in range(n):
                if macd[i] is None or sig[i] is None:
                    continue
                if i < first + self.signal - 1:
                    continue
                signal_line[i] = sig[i]
                hist[i] = float(macd[i]) - float(sig[i])  # type: ignore[arg-type]

        return {"macd": macd, "signal": signal_line, "histogram": hist}

    def calculate_frame(self, df):  # pragma: no cover - export adapter
        import pandas as pd

        result = self.calculate(df["close"].astype(float).tolist())
        return pd.DataFrame(result, index=df.index)
