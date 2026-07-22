"""Sector strength ranking."""

from __future__ import annotations


def sector_strength(sector_returns: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(sector_returns.items(), key=lambda kv: kv[1], reverse=True)
