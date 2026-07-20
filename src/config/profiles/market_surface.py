"""Market-surface profiles for TradeXV2.

This module is the *source of truth* for the market conventions the rest of
the codebase reads via :class:`domain.conventions.MarketSurface`. A
default surface is registered that is byte-for-byte equal to the legacy
hardcoded constants (NSE / INR / paisa x100 / tick 0.05 / lot 1 / risk-free
0.065), and additional surfaces can be registered for other exchanges or
simulated venues.

Usage::

    from config.profiles.market_surface import get_market_surface

    surface = get_market_surface()            # default "NSE_INR"
    surface = get_market_surface("NSE_INR")
"""

from __future__ import annotations

from domain.conventions import (
    DEFAULT_MARKET_SURFACE,
    MarketSurface,
)

#: Registry of named market surfaces. Add more via :func:`register_market_surface`.
MARKET_SURFACES: dict[str, MarketSurface] = {
    "NSE_INR": DEFAULT_MARKET_SURFACE,
}


def get_market_surface(name: str = "NSE_INR") -> MarketSurface:
    """Return the named market surface.

    Args:
        name: Registered surface name. Defaults to ``"NSE_INR"``.

    Raises:
        KeyError: If *name* is not registered.
    """
    try:
        return MARKET_SURFACES[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown market surface '{name}'. Available: {sorted(MARKET_SURFACES)}"
        ) from exc


def register_market_surface(name: str, surface: MarketSurface) -> None:
    """Register (or replace) a named market surface."""
    MARKET_SURFACES[name] = surface


__all__ = [
    "MARKET_SURFACES",
    "MarketSurface",
    "get_market_surface",
    "register_market_surface",
]
