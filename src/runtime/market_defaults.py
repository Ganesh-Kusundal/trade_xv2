"""Composition-edge market defaults from MarketSurface (TOS-P5-030).

Domain request objects may still carry literal defaults for backward
compatibility; new wiring should call these helpers so exchange/currency
come from the configured surface, not hardcoded NSE/INR.
"""

from __future__ import annotations

from domain.conventions import DEFAULT_MARKET_SURFACE, MarketSurface


def get_default_surface() -> MarketSurface:
    try:
        from config.profiles.market_surface import get_market_surface

        return get_market_surface()
    except Exception:
        return DEFAULT_MARKET_SURFACE


def default_exchange() -> str:
    return get_default_surface().exchange


def default_currency() -> str:
    return get_default_surface().currency


def default_risk_free_rate() -> float:
    return float(get_default_surface().risk_free_rate)


__all__ = [
    "default_currency",
    "default_exchange",
    "default_risk_free_rate",
    "get_default_surface",
]
