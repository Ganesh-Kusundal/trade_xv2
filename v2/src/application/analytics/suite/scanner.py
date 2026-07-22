"""Momentum scan over close sequences keyed by symbol."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MomentumSignal:
    symbol: str
    momentum: float


def momentum_scan(bars_by_symbol: dict[str, list[float]]) -> list[MomentumSignal]:
    """Rank symbols by simple return (last/first - 1). Skips empty/<2 bars."""
    signals: list[MomentumSignal] = []
    for symbol, closes in bars_by_symbol.items():
        if len(closes) < 2 or closes[0] == 0:
            continue
        mom = closes[-1] / closes[0] - 1.0
        signals.append(MomentumSignal(symbol=symbol, momentum=mom))
    signals.sort(key=lambda s: s.momentum, reverse=True)
    return signals
