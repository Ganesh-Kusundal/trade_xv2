"""Greeks value object — immutable, never a mutable dict."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Greeks:
    """Option greeks. Immutable value object exposed as ``option.greeks``."""

    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")

    @classmethod
    def from_dict(cls, data: dict | None) -> "Greeks":
        if not data:
            return cls.zero()

        def _dec(x: object) -> Decimal:
            try:
                return Decimal(str(x))
            except (TypeError, ValueError):
                return Decimal("0")

        return cls(
            delta=_dec(data.get("delta")),
            gamma=_dec(data.get("gamma")),
            theta=_dec(data.get("theta")),
            vega=_dec(data.get("vega")),
            rho=_dec(data.get("rho")),
        )

    @classmethod
    def zero(cls) -> "Greeks":
        return cls()
