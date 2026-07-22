"""Report metrics from an equity curve."""

from __future__ import annotations

import math
import statistics


def sharpe(
    equity: list[float],
    risk_free: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    if len(equity) < 2:
        return 0.0
    rets = [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity))]
    if len(rets) < 2:
        return 0.0
    excess = [r - risk_free / periods_per_year for r in rets]
    vol = statistics.stdev(excess)
    if vol == 0:
        return 0.0
    return (statistics.mean(excess) / vol) * math.sqrt(periods_per_year)


def max_drawdown(equity: list[float]) -> float:
    """Peak-to-trough drawdown as a positive fraction of peak."""
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > worst:
                worst = dd
    return worst
