"""Surface analytics value objects derived from option chains.

These are immutable, frozen value objects. They carry no broker logic and no
transport awareness — only the numeric surface data and pure derivations over
it. They are produced by :class:`~domain.options.option_chain.OptionChain` but
never reach back into a data source.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.options.greeks import Greeks


@dataclass(frozen=True, slots=True)
class GreeksSurface:
    """Greeks across strikes for a single expiry.

    ``data`` maps each strike to its (call) ``Greeks`` value object.
    """

    underlying: str
    expiry: str
    spot: Decimal | None
    data: dict[Decimal, Greeks]

    def at(self, strike) -> Greeks:
        """Return the ``Greeks`` for ``strike`` (zero Greeks if absent)."""
        return self.data.get(Decimal(str(strike)), Greeks.zero())

    def delta_exposure(self) -> Decimal:
        """Unweighted aggregate delta across the whole surface."""
        return sum((g.delta for g in self.data.values()), Decimal("0"))

    def gamma_exposure(self) -> Decimal:
        """Unweighted aggregate gamma across the whole surface."""
        return sum((g.gamma for g in self.data.values()), Decimal("0"))


@dataclass(frozen=True, slots=True)
class IVSurface:
    """Implied-volatility surface across strikes for a single expiry.

    ``data`` maps each strike to ``(call_iv, put_iv)``.
    """

    underlying: str
    expiry: str
    spot: Decimal | None
    data: dict[Decimal, tuple[Decimal | None, Decimal | None]]

    def at(self, strike) -> tuple[Decimal | None, Decimal | None]:
        """Return ``(call_iv, put_iv)`` for ``strike`` (``(None, None)`` if absent)."""
        return self.data.get(Decimal(str(strike)), (None, None))

    def atm_iv(self) -> Decimal | None:
        """IV at the strike nearest spot (prefers a non-``None`` quote)."""
        if not self.data:
            return None
        if self.spot is not None:
            strike = min(self.data, key=lambda k: abs(k - self.spot))
        else:
            strike = min(self.data)
        call_iv, put_iv = self.data[strike]
        for iv in (call_iv, put_iv):
            if iv is not None:
                return iv
        return None

    def skew(self) -> Decimal | None:
        """Call IV just above ATM minus put IV just below ATM.

        A positive value indicates the classic downward skew (puts richer than
        calls). Returns ``None`` when there is not both a higher and a lower
        strike than ATM to measure against.
        """
        if not self.data:
            return None
        strikes = sorted(self.data)
        atm = (
            min(strikes, key=lambda k: abs(k - self.spot))
            if self.spot is not None
            else strikes[len(strikes) // 2]
        )
        above = [k for k in strikes if k > atm]
        below = [k for k in strikes if k < atm]
        if not above or not below:
            return None
        call_iv_above = self.data[above[0]][0]
        put_iv_below = self.data[below[-1]][1]
        if call_iv_above is None or put_iv_below is None:
            return None
        return call_iv_above - put_iv_below


@dataclass(frozen=True, slots=True)
class VolatilitySurface:
    """Term structure of :class:`IVSurface` keyed by expiry string."""

    underlying: str
    surfaces: dict[str, IVSurface]

    def term_structure(self, strike) -> list[tuple[str, Decimal | None]]:
        """Call IV at ``strike`` for each expiry, ordered by expiry date."""
        result: list[tuple[str, Decimal | None]] = []
        for expiry in sorted(self.surfaces):
            call_iv, _ = self.surfaces[expiry].at(strike)
            result.append((expiry, call_iv))
        return result
