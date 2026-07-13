"""Market conventions — exchange/exposure value objects.

A :class:`MarketSurface` carries the market-wide conventions that domain and
market-data code used to embed as literals (``"NSE"``, ``"INR"``, paisa
scaling, tick size, lot size, risk-free rate). Code that needs these
conventions should *read* them from an injected ``MarketSurface`` instead of
embedding broker/market assumptions directly.

This module ships a :data:`DEFAULT_MARKET_SURFACE` whose values are byte-for-byte
equal to the legacy hardcoded constants that previously lived in
``domain.constants.market`` (NSE, INR, paisa = x100, tick = 0.05, lot = 1,
risk-free = 0.065). ``config.profiles.market_surface`` adds further surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

#: Legacy number of paise per rupee. Prices on Indian exchanges are often
#: quoted in paise (1/100 of a rupee) on the binary wire.
PAISA_SCALE: int = 100

#: Default price scale used when constructing a surface without one.
DEFAULT_PRICE_SCALE: int = PAISA_SCALE


@dataclass(frozen=True)
class MarketSurface:
    """Market-wide conventions for a single exchange/segment surface.

    Attributes
    ----------
    exchange:
        Canonical short exchange code (e.g. ``"NSE"``).
    currency:
        ISO-style trading currency code (e.g. ``"INR"``).
    price_tick:
        Minimum price increment as a :class:`~decimal.Decimal`.
    lot_size:
        Standard contract lot size (1 for equity/cash).
    risk_free_rate:
        Annual risk-free rate used for derivatives/P&L math.
    price_scale:
        Sub-unit divisor for the paisa<->rupee convention (default 100).
    """

    exchange: str
    currency: str
    price_tick: Decimal
    lot_size: int
    risk_free_rate: float
    price_scale: int = DEFAULT_PRICE_SCALE

    # ── Price-convention helpers ──────────────────────────────────────────

    def to_paisa(self, rupee: Decimal | float | int | str) -> int:
        """Convert a rupee amount to an integer paisa count.

        Uses ``ROUND_HALF_UP`` (the standard NSE/BSE rounding convention).
        """
        return int(
            (Decimal(rupee) * self.price_scale).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )

    def to_rupee(self, paisa: Decimal | float | int | str) -> Decimal:
        """Convert an integer paisa count back to a rupee :class:`Decimal`."""
        return (Decimal(paisa) / Decimal(self.price_scale)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def snap_to_tick(self, price: Decimal | float | int | str) -> Decimal:
        """Round *price* to the nearest multiple of :attr:`price_tick`.

        Mirrors ``domain.value_objects.price.snap_to_tick`` but reads the tick
        from this surface.
        """
        tick = self.price_tick
        if tick <= Decimal("0"):
            raise ValueError(f"price_tick must be positive, got {tick}")
        p = Decimal(price)
        if p < Decimal("0"):
            raise ValueError(f"price must be non-negative, got {p}")
        ticks = (p / tick).to_integral_value(rounding=ROUND_HALF_UP)
        return (ticks * tick).quantize(tick)

    def is_tick_aligned(
        self,
        price: Decimal | float | int | str,
        *,
        tolerance: Decimal = Decimal("0.0001"),
    ) -> bool:
        """Return ``True`` if *price* is an exact multiple of :attr:`price_tick`."""
        tick = self.price_tick
        if tick <= Decimal("0"):
            raise ValueError(f"price_tick must be positive, got {tick}")
        p = Decimal(price)
        if p < Decimal("0"):
            raise ValueError(f"price must be non-negative, got {p}")
        if p == Decimal("0"):
            return True
        remainder = p % tick
        return remainder <= tolerance or (tick - remainder) <= tolerance


#: Default market surface — values must stay identical to the legacy constants
#: previously hardcoded across ``domain`` (NSE / INR / paisa x100 / tick 0.05 /
#: lot 1 / risk-free 0.065). Change these ONLY when the legacy behaviour
#: itself changes; the test-suite asserts byte-for-byte equality.
DEFAULT_MARKET_SURFACE: MarketSurface = MarketSurface(
    exchange="NSE",
    currency="INR",
    price_tick=Decimal("0.05"),
    lot_size=1,
    risk_free_rate=0.065,
    price_scale=PAISA_SCALE,
)


def get_default_market_surface() -> MarketSurface:
    """Return the default (legacy-equivalent) market surface."""
    return DEFAULT_MARKET_SURFACE


__all__ = [
    "DEFAULT_MARKET_SURFACE",
    "DEFAULT_PRICE_SCALE",
    "PAISA_SCALE",
    "MarketSurface",
    "get_default_market_surface",
]
