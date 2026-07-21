"""Shared simulation models — mode-agnostic enums, config, trade, and position bases.

Paper and replay engines both inherit from these shared classes so that
common fields, validation, and domain-conversion logic are defined once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from domain.enums import PositionSide, Side
from domain.trading_costs import CommissionModel, IndianMarketFees
from domain.market_enums import ExchangeId


class FillModel(str, Enum):
    """Fill price model for simulated trades (paper + replay)."""

    CURRENT_CLOSE = "current_close"
    NEXT_OPEN = "next_open"


# ---------------------------------------------------------------------------
# SimConfig — shared base for PaperConfig / ReplayConfig
# ---------------------------------------------------------------------------


@dataclass
class SimConfig:
    """Common configuration fields shared by paper and replay engines.

    Subclasses add mode-specific fields (e.g. ``max_positions`` for paper,
    ``mode`` / ``slippage_model`` for replay).
    """

    initial_capital: float = 100_000.0
    slippage_pct: float = 0.01
    commission_flat: float = 0.0
    commission_model: CommissionModel = CommissionModel.FLAT
    indian_market_fees: IndianMarketFees = field(default_factory=IndianMarketFees)
    fill_model: FillModel = FillModel.NEXT_OPEN
    warmup_bars: int = 20
    window_size: int = 100
    max_position_pct: float = 25.0
    fail_closed_features: bool = True


# ---------------------------------------------------------------------------
# SimTrade — shared base for PaperTrade / SimulatedTrade
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimTrade:
    """Common trade fields shared by paper and replay engines.

    Uses ``Side`` enum (not str).  Both ``PaperTrade`` and
    ``SimulatedTrade`` inherit from this class and add mode-specific fields.
    """

    symbol: str
    side: Side
    entry_price: float
    quantity: int
    entry_time: datetime | None = None
    exit_price: float | None = None
    exit_time: datetime | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0
    slippage_cost: float = 0.0
    strategy: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_domain_trade(self) -> Any:
        """Convert to canonical ``domain.entities.Trade`` via shared helper.

        ponytail: SimTrade stays a thin session record; domain Trade is SSOT.
        The conversion lives in ``analytics.shared.trade_types`` so replay
        and paper share one mapping.
        """
        from analytics.shared.trade_types import sim_trade_to_domain

        return sim_trade_to_domain(
            trade_id=f"sim:{self.symbol}:{id(self)}",
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            price=Decimal(str(self.exit_price or self.entry_price)),
            trade_value=Decimal(str(abs(self.pnl))) if self.pnl != 0 else Decimal("0"),
        )


# ---------------------------------------------------------------------------
# SimPosition — shared base for PaperPosition / SimulatedPosition
# ---------------------------------------------------------------------------


@dataclass
class SimPosition:
    """Common position fields shared by paper and replay engines.

    Uses ``PositionSide`` enum (not str).  Both ``PaperPosition`` and
    ``SimulatedPosition`` inherit from this class and add mode-specific fields.
    """

    symbol: str
    side: PositionSide
    entry_price: float
    quantity: int
    entry_time: datetime
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy: str = ""
    current_price: float = 0.0

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    @property
    def market_value(self) -> float:
        """Mark-to-market position value (qty x latest price)."""
        px = self.current_price if self.current_price > 0 else self.entry_price
        return px * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        if self.side == PositionSide.LONG:
            return (self.current_price - self.entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            return (self.entry_price - self.current_price) * self.quantity
        return 0.0

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        if self.side == PositionSide.LONG:
            return ((self.current_price / self.entry_price) - 1) * 100
        elif self.side == PositionSide.SHORT:
            return ((self.entry_price / self.current_price) - 1) * 100
        return 0.0

    def update_price(self, price: float) -> None:
        self.current_price = price

    def to_domain_position(self) -> Any:
        """Convert to canonical ``domain.entities.Position`` (REF-016).

        Price fields are coerced to ``Decimal``.
        """
        from domain.entities import Position

        qty = self.quantity if self.side == PositionSide.LONG else -self.quantity
        return Position(
            symbol=self.symbol,
            exchange=ExchangeId.NSE,
            quantity=qty,
            avg_price=Decimal(str(self.entry_price)),
            ltp=Decimal(str(self.current_price)),
        )
