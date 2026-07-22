"""Pure indicators: SMA, EMA, RSI."""

from __future__ import annotations


def sma(values: list[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    out: list[float] = []
    window = sum(values[:period])
    out.append(window / period)
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out.append(window / period)
    return out


def ema(values: list[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out = [seed]
    prev = seed
    for v in values[period:]:
        prev = alpha * v + (1.0 - alpha) * prev
        out.append(prev)
    return out


def rsi(values: list[float], period: int = 14) -> list[float]:
    """Wilder RSI; returns one value per bar from index `period` onward."""
    if period <= 0 or len(values) <= period:
        return []
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    out: list[float] = []

    def _rsi(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out.append(_rsi(avg_gain, avg_loss))
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out.append(_rsi(avg_gain, avg_loss))
    return out
