"""OMS Service layer for diagnostics and operation terminal."""

from __future__ import annotations

from decimal import Decimal

from brokers.common.core.domain import Order, OrderResponse, OrderStatus, Side, Trade
from cli.services.broker_service import BrokerService


class OmsService:
    """Interfaces with active broker order book and monitors OMS flows."""

    def __init__(self, broker_service: BrokerService):
        self._broker_service = broker_service

    def get_order_stats(self) -> dict[str, int]:
        """Collect order counts by status."""
        orders = self._broker_service.active_broker.get_orders()
        stats = {
            "pending": 0,
            "open": 0,
            "filled": 0,
            "rejected": 0,
            "cancelled": 0,
        }
        for o in orders:
            status = o.status
            if status == OrderStatus.OPEN:
                stats["open"] += 1
            elif status == OrderStatus.PARTIALLY_FILLED:
                stats["pending"] += 1
            elif status == OrderStatus.FILLED:
                stats["filled"] += 1
            elif status == OrderStatus.REJECTED:
                stats["rejected"] += 1
            elif status == OrderStatus.CANCELLED:
                stats["cancelled"] += 1
        return stats

    def get_orders(self, status_filter: str | None = None) -> list[Order]:
        """Fetch orders with optional status filter."""
        orders = self._broker_service.active_broker.get_orders()
        if not status_filter:
            return orders

        filt = status_filter.upper()
        if filt == "PENDING":
            return [
                o for o in orders if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
            ]
        return [o for o in orders if o.status.value == filt]

    def get_trades(self) -> list[Trade]:
        """Fetch trades for the day."""
        return self._broker_service.active_broker.get_trades()

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
    ) -> OrderResponse:
        """Place order via active broker."""
        return self._broker_service.active_broker.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        return self._broker_service.active_broker.cancel_order(order_id)
