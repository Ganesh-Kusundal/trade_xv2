"""Portfolio module -- portfolio summary and tracking.

Provides a portfolio manager that aggregates positions, holdings, and
P&L from a broker-like object into a single summary snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, List

from brokers.common.core.domain import Holding, Position

# -- Portfolio Summary -------------------------------------------------------


@dataclass
class PortfolioSummary:
    """Point-in-time snapshot of portfolio metrics."""

    total_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    position_count: int = 0
    holding_count: int = 0


# -- Portfolio Manager -------------------------------------------------------


class PortfolioManager:
    """Aggregates portfolio data from a broker-like object.

    The *broker* must expose ``get_positions()`` and ``get_holdings()``
    methods that return lists of :class:`Position` and :class:`Holding`
    respectively.
    """

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    def get_summary(self) -> PortfolioSummary:
        """Build and return a :class:`PortfolioSummary`."""
        positions: list[Position] = self._broker.get_positions()
        holdings: list[Holding] = self._broker.get_holdings()

        total_value = Decimal("0")
        unrealized_pnl = Decimal("0")
        realized_pnl = Decimal("0")

        for pos in positions:
            total_value += Decimal(str(abs(pos.quantity))) * pos.ltp
            unrealized_pnl += pos.unrealized_pnl
            realized_pnl += pos.realized_pnl

        for h in holdings:
            total_value += Decimal(str(h.quantity)) * h.ltp
            unrealized_pnl += h.pnl

        return PortfolioSummary(
            total_value=total_value,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            position_count=len(positions),
            holding_count=len(holdings),
        )
