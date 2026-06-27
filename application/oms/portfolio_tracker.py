"""PortfolioTracker — reads position/capital state from production OMS.

Eliminates shadow state in replay/paper engines by providing a read-only
view of the OMS state. Engines call PortfolioTracker instead of maintaining
their own position/capital tracking.

Usage:
    tracker = PortfolioTracker(order_manager, position_manager)
    capital = tracker.get_capital()
    positions = tracker.get_positions()
    equity = tracker.get_equity(current_prices)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from domain import Position, Trade

logger = logging.getLogger(__name__)


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state read from OMS."""

    capital: Decimal
    positions: list[Position]
    realized_pnl: Decimal
    unrealized_pnl: Decimal

    @property
    def equity(self) -> Decimal:
        """Total equity = capital + realized + unrealized PnL."""
        return self.capital + self.realized_pnl + self.unrealized_pnl


class PortfolioTracker:
    """Read-only portfolio state tracker backed by production OMS.

    This eliminates shadow state in replay/paper engines by reading
    position and capital state directly from the OMS.

    The tracker subscribes to TRADE_APPLIED events to maintain an
    atomic capital ledger, but position state is always read from
    PositionManager.
    """

    def __init__(
        self,
        order_manager: Any,
        position_manager: Any,
        initial_capital: Decimal = Decimal("0"),
    ) -> None:
        self._oms = order_manager
        self._positions = position_manager
        self._initial_capital = initial_capital
        self._capital = initial_capital
        self._realized_pnl = Decimal("0")
        self._trades: list[Trade] = []

    def get_capital(self) -> Decimal:
        """Return current available capital."""
        return self._capital

    def get_positions(self) -> list[Position]:
        """Return current positions from OMS."""
        return self._positions.get_all_positions()

    def get_position(self, symbol: str, exchange: str = "NSE") -> Position | None:
        """Return position for a specific symbol."""
        return self._positions.get_position(symbol, exchange)

    def get_trades(self) -> list[Trade]:
        """Return all executed trades."""
        return self._trades

    def get_equity(self, current_prices: dict[str, Decimal] | None = None) -> Decimal:
        """Calculate total equity = capital + realized + unrealized PnL.

        If current_prices is provided, unrealized PnL is calculated
        from actual market prices. Otherwise, uses OMS position LTP.
        """
        realized = self._realized_pnl
        unrealized = self._calculate_unrealized_pnl(current_prices)
        return self._capital + realized + unrealized

    def on_trade_applied(self, trade: Trade) -> None:
        """Handle TRADE_APPLIED event — update capital and trade list.

        This is the ONLY method that mutates state. It should be called
        from an event subscriber, not directly by engines.
        """
        self._trades.append(trade)

        # Update capital based on trade
        if trade.side == "BUY":
            self._capital -= Decimal(str(trade.quantity)) * trade.price
        else:
            self._capital += Decimal(str(trade.quantity)) * trade.price

        # Calculate PnL from trade value
        if trade.trade_value > 0:
            self._realized_pnl += trade.trade_value - (Decimal(str(trade.quantity)) * trade.price)

        logger.debug(
            "portfolio_tracker: trade applied",
            extra={
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": float(trade.price),
                "trade_value": float(trade.trade_value),
                "capital": float(self._capital),
            },
        )

    def _calculate_unrealized_pnl(
        self, current_prices: dict[str, Decimal] | None = None
    ) -> Decimal:
        """Calculate unrealized PnL from open positions."""
        total = Decimal("0")
        for pos in self._positions.get_all_positions():
            if pos.quantity == 0:
                continue

            # Get current price
            if current_prices and pos.symbol in current_prices:
                ltp = current_prices[pos.symbol]
            else:
                ltp = pos.ltp or Decimal("0")

            # Calculate unrealized PnL
            if pos.quantity > 0:
                # Long position
                total += (ltp - pos.avg_price) * Decimal(str(pos.quantity))
            else:
                # Short position
                total += (pos.avg_price - ltp) * Decimal(str(abs(pos.quantity)))

        return total

    def snapshot(self, current_prices: dict[str, Decimal] | None = None) -> PortfolioSnapshot:
        """Take a point-in-time snapshot of portfolio state."""
        return PortfolioSnapshot(
            capital=self._capital,
            positions=self.get_positions(),
            realized_pnl=self._realized_pnl,
            unrealized_pnl=self._calculate_unrealized_pnl(current_prices),
        )
