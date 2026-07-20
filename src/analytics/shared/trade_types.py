"""Single Trade/Position for simulation — shared conversion to domain Trade.

Replay (``SimulatedTrade``) and paper (``PaperTrade``) session records both
convert to the canonical ``domain.entities.Trade`` via the same helper,
:func:`sim_trade_to_domain`. Keeping the conversion in one place is the
zero-parity guarantee: backtest/replay/paper/live all produce identical
domain trades (D7/D12).
"""

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
        return sim_trade_to_domain(
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


def sim_trade_to_domain(
    *,
    trade_id: str,
    symbol: str,
    side: str,
    quantity: int,
    price: Decimal,
    trade_value: Decimal | None = None,
) -> Any:
    """Single conversion path from a simulated trade to a canonical domain Trade.

    Used by both ``SimulatedTrade.to_domain_trade`` (replay) and
    ``PaperTrade.to_domain_trade`` (paper) so the trade→domain mapping is
    defined exactly once. Zero-parity: replay and paper emit structurally
    identical domain trades.
    """
    from domain.entities.trade import build_domain_trade

    return build_domain_trade(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        trade_value=trade_value if trade_value is not None else Decimal("0"),
    )
