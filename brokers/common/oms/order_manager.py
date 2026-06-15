"""Central order management system.

Single owner for order state. All order placement, updates, and queries go
through this manager. It is protected by one ``threading.RLock`` and uses
immutable ``Order`` / ``Trade`` value objects.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable

from brokers.common.core.domain import Order, OrderStatus, OrderType, ProductType, Side, Trade
from brokers.common.event_bus import DomainEvent, EventBus
from brokers.common.oms.risk_manager import RiskManager


@dataclass(frozen=True)
class OrderRequest:
    """Plain request object for placing an order."""

    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "exchange", self.exchange.upper())
        object.__setattr__(self, "price", Decimal(str(self.price)))
        if not self.correlation_id:
            object.__setattr__(self, "correlation_id", f"ord:{uuid.uuid4().hex[:12]}")


class OrderResult:
    def __init__(self, success: bool, order: Order | None = None, error: str | None = None):
        self.success = success
        self.order = order
        self.error = error


class OrderManager:
    """Thread-safe order book with idempotency, risk checks, and event publishing."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._orders_by_correlation: dict[str, Order] = {}
        self._event_bus = event_bus
        self._risk_manager = risk_manager

    @property
    def risk_manager(self) -> RiskManager | None:
        return self._risk_manager

    def check_order(self, order: Order) -> bool:
        """Return True if the order passes the configured risk checks."""
        if self._risk_manager is None:
            return True
        return self._risk_manager.check_order(order).allowed

    # ── Public API ──────────────────────────────────────────────────────────

    def place_order(
        self,
        request: OrderRequest,
        submit_fn: Callable[[OrderRequest], Order] | None = None,
    ) -> OrderResult:
        """Place an order idempotently.

        If ``submit_fn`` is provided, the order is sent to the broker under the
        manager's lock and the result is recorded. If ``submit_fn`` is None, the
        order is recorded as OPEN and the caller is responsible for sending it.
        """
        with self._lock:
            existing = self._orders_by_correlation.get(request.correlation_id)
            if existing is not None:
                return OrderResult(success=True, order=existing)

            order_id = f"OM-{uuid.uuid4().hex[:12]}"
            order = Order(
                order_id=order_id,
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                price=request.price,
                product_type=request.product_type,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(timezone.utc),
                correlation_id=request.correlation_id,
            )

            if self._risk_manager is not None:
                risk_result = self._risk_manager.check_order(order)
                if not risk_result.allowed:
                    return OrderResult(success=False, error=risk_result.reason)

            if submit_fn is not None:
                try:
                    order = submit_fn(request)
                except Exception as exc:
                    return OrderResult(success=False, error=str(exc))

            self._orders[order.order_id] = order
            self._orders_by_correlation[request.correlation_id] = order
            self._publish("ORDER_PLACED", order)
            return OrderResult(success=True, order=order)

    def upsert_order(self, order: Order) -> None:
        """Update or insert an order (used by broker event handlers)."""
        with self._lock:
            self._orders[order.order_id] = order
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = order
            self._publish("ORDER_UPDATED", order)

    def record_trade(self, trade: Trade) -> None:
        """Record a trade and update the parent order."""
        with self._lock:
            order = self._orders.get(trade.order_id)
            if order is None:
                return
            new_filled = order.filled_quantity + trade.quantity
            new_avg = self._compute_avg_price(order, trade)
            new_status = OrderStatus.FILLED if new_filled >= order.quantity else OrderStatus.PARTIALLY_FILLED
            updated = order.with_fill(new_filled, new_avg).with_status(new_status)
            self._orders[order.order_id] = updated
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = updated
            self._publish("ORDER_UPDATED", updated)

    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)

    def get_order_by_correlation(self, correlation_id: str) -> Order | None:
        with self._lock:
            return self._orders_by_correlation.get(correlation_id)

    def get_orders(
        self,
        symbol: str | None = None,
        status: OrderStatus | None = None,
    ) -> list[Order]:
        with self._lock:
            orders = list(self._orders.values())
        if symbol is not None:
            orders = [o for o in orders if o.symbol == symbol.upper()]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return orders

    def get_all_orders(self) -> list[dict]:
        """Return all orders as list of dicts for reconciliation compatibility."""
        with self._lock:
            return [
                {
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "exchange": o.exchange,
                    "side": o.side.value if hasattr(o.side, "value") else str(o.side),
                    "order_type": o.order_type.value if hasattr(o.order_type, "value") else str(o.order_type),
                    "quantity": o.quantity,
                    "filled_quantity": o.filled_quantity,
                    "price": str(o.price),
                    "avg_price": str(o.avg_price),
                    "product_type": o.product_type.value if hasattr(o.product_type, "value") else str(o.product_type),
                    "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                    "timestamp": o.timestamp.isoformat() if hasattr(o.timestamp, "isoformat") else str(o.timestamp),
                }
                for o in self._orders.values()
            ]

    def cancel_order(self, order_id: str) -> OrderResult:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                return OrderResult(success=False, error="Order not found")
            if order.status.is_terminal:
                return OrderResult(success=False, error="Order already final")
            updated = order.with_status(OrderStatus.CANCELLED)
            self._orders[order_id] = updated
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = updated
            self._publish("ORDER_CANCELLED", updated)
            return OrderResult(success=True, order=updated)

    # ── Event handlers ──────────────────────────────────────────────────────

    def on_order_update(self, event: DomainEvent) -> None:
        """Handle broker order-update events."""
        payload = event.payload
        order = payload.get("order")
        if isinstance(order, Order):
            self.upsert_order(order)

    def on_trade(self, event: DomainEvent) -> None:
        """Handle broker trade events."""
        payload = event.payload
        trade = payload.get("trade")
        if isinstance(trade, Trade):
            self.record_trade(trade)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _publish(self, event_type: str, obj: Order | Trade) -> None:
        if self._event_bus is None:
            return
        symbol = obj.symbol if hasattr(obj, "symbol") else None
        payload: dict = {"order": obj} if isinstance(obj, Order) else {"trade": obj}
        self._event_bus.publish(
            DomainEvent.now(event_type, payload, symbol=symbol, source="OrderManager")
        )

    @staticmethod
    def _compute_avg_price(order: Order, trade: Trade) -> Decimal:
        if order.filled_quantity == 0:
            return trade.price
        total_value = order.avg_price * Decimal(order.filled_quantity) + trade.price * Decimal(trade.quantity)
        total_qty = order.filled_quantity + trade.quantity
        return total_value / Decimal(total_qty) if total_qty else Decimal("0")
