"""Order-flow imbalance from bid/ask sizes."""

from __future__ import annotations


def imbalance(bid_size: float, ask_size: float) -> float:
    total = bid_size + ask_size
    if total == 0:
        return 0.0
    return (bid_size - ask_size) / total
