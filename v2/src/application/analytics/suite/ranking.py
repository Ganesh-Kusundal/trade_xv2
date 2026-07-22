"""Universe ranking helpers."""

from __future__ import annotations


def rank_by_return(returns: dict[str, float]) -> list[str]:
    return sorted(returns, key=returns.__getitem__, reverse=True)
