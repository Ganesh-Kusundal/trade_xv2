"""Future value object — a derivative contract with expiry and lot size.

Distinct from the existing FutureContract entity which is a data transfer
object from broker adapters. Future is a domain-level value object with
validation invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Future:
    """Domain value object for a futures contract."""

    symbol: str
    exchange: str
    expiry: date
    lot_size: int
    tick_size: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if self.lot_size < 1:
            raise ValueError(f"lot_size must be >= 1, got {self.lot_size}")
        if self.tick_size <= 0:
            raise ValueError(f"tick_size must be > 0, got {self.tick_size}")

    @property
    def key(self) -> str:
        return f"{self.exchange}:{self.symbol}:{self.expiry.isoformat()}"

    @property
    def is_expired(self) -> bool:
        from datetime import date as _date

        return self.expiry < _date.today()
