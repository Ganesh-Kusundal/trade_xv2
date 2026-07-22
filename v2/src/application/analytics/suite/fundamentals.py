"""Fundamentals ratios."""

from __future__ import annotations


def pe_ratio(price: float, eps: float) -> float:
    if eps == 0:
        raise ValueError("eps must be non-zero")
    return price / eps
