"""Market breadth: advance / decline."""

from __future__ import annotations


def advance_decline(returns: list[float]) -> tuple[int, int, float]:
    """Return (advances, declines, adv/dec ratio). Flat (0) ignored in counts."""
    adv = sum(1 for r in returns if r > 0)
    dec = sum(1 for r in returns if r < 0)
    ratio = (adv / dec) if dec else float("inf") if adv else 0.0
    return adv, dec, ratio
