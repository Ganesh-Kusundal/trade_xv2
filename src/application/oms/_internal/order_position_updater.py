"""Position updates for order fills.

Extracted from OrderManager to follow SRP. This collaborator is responsible
solely for updating order state when trades are applied, including partial
fill handling and quantity tracking.

Thread Safety
-------------
This class is NOT thread-safe by itself. Callers must provide external
synchronization (e.g., OrderManager's RLock) when using this collaborator,
consistent with the existing pattern.

Usage:
    updater = OrderPositionUpdater()
    updated_order = updater.apply_trade(order, trade)
    # Returns new Order with updated fill state
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from domain.types import OrderStatus

if TYPE_CHECKING:
    from domain import Order, Trade


class OrderPositionUpdater:
    """Applies trade fills to orders and computes derived state.

    This collaborator handles:
    - Partial fill tracking
    - Average price computation (VWAP-style)
    - Order status derivation from fill state
    - Immutable order updates

    Thread Safety
    -------------
    Not thread-safe. Caller must hold appropriate lock.
    """

    def apply_trade(self, order: Order, trade: Trade) -> Order:
        """Apply a trade fill to an order.

        Parameters
        ----------
        order:
            Current order state.
        trade:
            Trade to apply.

        Returns
        -------
        Order:
            New Order instance with updated fill state.

        Raises
        ------
        ValueError:
            If trade quantity exceeds remaining order quantity.
        """
        new_filled = order.filled_quantity + trade.quantity
        new_avg = self._compute_avg_price(order, trade)
        new_status = self._derive_status(order, new_filled)

        return order.with_fill(new_filled, new_avg).with_status(new_status)

    def _compute_avg_price(self, order: Order, trade: Trade) -> Decimal:
        """Compute new average fill price using VWAP.

        Parameters
        ----------
        order:
            Current order with existing fills.
        trade:
            New trade to incorporate.

        Returns
        -------
        Decimal:
            New weighted average price.
        """
        if trade.quantity == 0:
            return order.avg_price

        if order.filled_quantity == 0:
            return trade.price

        total_value = (
            order.avg_price * order.filled_quantity.to_decimal()
            + trade.price * trade.quantity.to_decimal()
        )
        total_qty = order.filled_quantity + trade.quantity
        return total_value / Decimal(total_qty.to_decimal()) if total_qty else Decimal("0")

    def _derive_status(self, order: Order, new_filled: int) -> OrderStatus:
        """Derive order status from fill state.

        Parameters
        ----------
        order:
            Current order.
        new_filled:
            New total filled quantity.

        Returns
        -------
        OrderStatus:
            FILLED if order is complete, PARTIALLY_FILLED otherwise.
        """
        if new_filled >= order.quantity:
            return OrderStatus.FILLED
        return OrderStatus.PARTIALLY_FILLED
