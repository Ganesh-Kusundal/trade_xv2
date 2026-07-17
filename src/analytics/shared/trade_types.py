"""Single Trade/Position for simulation — eliminates 4 divergent shapes."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from domain.enums import Side

@dataclass(frozen=True)
class SimTrade:
    """Unified simulated trade for paper and replay engines."""
    trade_id: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    timestamp: datetime | None = None
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")

    def to_domain_trade(self) -> Any:
        """Convert to canonical domain Trade."""
        from domain.entities.trade import build_domain_trade
        return build_domain_trade(
            trade_id=self.trade_id,
            symbol=self.symbol,
            side=self.side.value,
            quantity=self.quantity,
            price=self.price,
        )

@dataclass(frozen=True)
class SimPosition:
    """Unified simulated position for paper and replay engines."""
    symbol: str
    side: Side
    quantity: int
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
