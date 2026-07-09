"""Strike selection result — instrument-based (CE/PE are Option objects)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.instruments.instrument import Option


@dataclass(frozen=True, slots=True)
class StrikeSelection:
    """Result of :meth:`OptionChain.select_strikes`.

    Always instrument-oriented: ``ce`` / ``pe`` are full :class:`Option`
    objects (stamped with chain OMS/data), never raw dicts.
    """

    style: str
    steps: int
    strike: Decimal | None  # ATM / shared strike when CE and PE share one
    ce: Any | None  # Option | None
    pe: Any | None  # Option | None
    ce_strike: Decimal | None = None
    pe_strike: Decimal | None = None

    @property
    def symbol_ce(self) -> str | None:
        return getattr(self.ce, "symbol", None) if self.ce is not None else None

    @property
    def symbol_pe(self) -> str | None:
        return getattr(self.pe, "symbol", None) if self.pe is not None else None
