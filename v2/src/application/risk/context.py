"""Risk DTOs — RiskContext snapshot + RiskCheckResult."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.entities import Position
from domain.value_objects import InstrumentId


@dataclass(frozen=True, slots=True)
class RiskCheckResult:
    approved: bool
    reason: str | None = None
    max_quantity: Decimal | None = None
    max_notional: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RiskContext:
    """Snapshot at check time — positions, PnL, rate, margin."""

    positions: dict[InstrumentId, Position]
    daily_pnl: Decimal
    order_count: int
    available_margin: Decimal
