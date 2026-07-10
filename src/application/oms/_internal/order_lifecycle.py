"""Order book lifecycle ops extracted from OrderManager.

Owns cancel / modify / upsert / place finalization against the in-memory
order maps.  OrderManager remains the public façade and lock owner.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from domain.events.types import EventType
from domain.types import OrderStatus

if TYPE_CHECKING:
    from application.oms._internal.order_audit_logger import OrderAuditLogger
    from application.oms._internal.order_state_validator import OrderStateValidator
    from application.oms.idempotency_guard import IdempotencyGuard
    from application.oms.order_manager import OmsOrderCommand, OrderResult
    from application.oms.risk_manager import RiskManager
    from application.oms.trade_recorder import TradeRecorder
    from domain.entities import Order


def order_as_recon_dict(order: Order) -> dict:
    """Serialize an order for reconciliation / external consumers."""
    return {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "exchange": order.exchange,
        "side": order.side.value,
        "order_type": order.order_type.value,
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "price": str(order.price),
        "avg_price": str(order.avg_price),
        "product_type": order.product_type.value,
        "status": order.status.value,
        "timestamp": order.timestamp.isoformat() if order.timestamp else "",
    }


def apply_modify_fields(order: Order, req: Any) -> Order:
    """Apply non-None modify fields to a local order (pure)."""
    updated = order
    if req.price is not None:
        updated = updated.with_price(req.price)
    if req.quantity is not None:
        updated = updated.with_quantity(req.quantity)
    if req.order_type is not None:
        updated = updated.with_order_type(req.order_type)
    return updated


def store_order(
    orders: dict[str, Order],
    orders_by_correlation: dict[str, Order],
    order: Order,
) -> None:
    """Write *order* into both book indexes (caller holds lock)."""
    orders[order.order_id] = order
    if order.correlation_id:
        orders_by_correlation[order.correlation_id] = order


class OrderLifecycle:
    """Cancel / modify / upsert / placement finalization for the OMS book."""

    def __init__(
        self,
        *,
        state_validator: OrderStateValidator,
        audit_logger: OrderAuditLogger,
        trade_recorder: TradeRecorder,
        idempotency_guard: IdempotencyGuard,
        risk_manager: RiskManager | None,
        publish: Callable[..., None],
        active_orders: Any | None = None,
    ) -> None:
        self._state_validator = state_validator
        self._audit_logger = audit_logger
        self._trade_recorder = trade_recorder
        self._idempotency_guard = idempotency_guard
        self._risk_manager = risk_manager
        self._publish = publish
        self._active_orders = active_orders

    def submit_to_broker(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        order: Order,
        request: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None,
    ) -> tuple[Order | None, OrderResult | None]:
        """Phase 3: Submit order to broker (no lock held around I/O).

        Returns (order, None) on success, or (None, OrderResult) on failure.
        """
        from application.oms.order_manager import OrderResult

        if submit_fn is None:
            return order, None
        # Record-then-submit: persist stub before broker I/O so a crash after
        # broker accept still leaves a reconcilable order in the book.
        with lock:
            orders[order.order_id] = order
            orders_by_correlation[request.correlation_id] = order
        try:
            order = submit_fn(request)
            return order, None
        except Exception as exc:
            self._publish(
                EventType.ORDER_REJECTED.value,
                order,
                reason=str(exc),
            )
            return None, OrderResult(success=False, error=str(exc))

    def record_and_publish(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        order: Order,
        request: OmsOrderCommand,
    ) -> None:
        """Phase 4: Record order in book and publish event."""
        with lock:
            self._idempotency_guard.release_pending(lock, request.correlation_id)
            prior = orders_by_correlation.get(request.correlation_id)
            if prior is not None and prior.order_id != order.order_id:
                orders.pop(prior.order_id, None)
            orders[order.order_id] = order
            orders_by_correlation[request.correlation_id] = order

        self._audit_logger.log_new_order(
            order.order_id,
            OrderStatus.OPEN,
            details={
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
            },
        )
        self._publish(EventType.ORDER_PLACED.value, order)
        if self._active_orders is not None:
            self._active_orders.inc()

    def upsert_order(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        order: Order,
    ) -> None:
        """Update or insert an order (used by broker event handlers)."""
        with lock:
            existing = orders.get(order.order_id)
            if existing is not None:
                self._state_validator.validate_transition(
                    order.order_id,
                    existing.status,
                    order.status,
                )

            store_order(orders, orders_by_correlation, order)

            if existing is not None and existing.status != order.status:
                self._audit_logger.log_state_change(
                    order.order_id,
                    existing.status,
                    order.status,
                )
                if order.status.is_terminal and self._active_orders is not None:
                    self._active_orders.dec()

            self._publish(EventType.ORDER_UPDATED.value, order)
            self._trade_recorder.flush_pending_trades_locked(
                lock, orders, orders_by_correlation, order.order_id
            )

    def cancel_order(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        order_id: str,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> OrderResult:
        """Cancel an order locally and optionally at the broker."""
        from application.oms.order_manager import OrderResult

        with lock:
            order = orders.get(order_id)
            if order is None:
                return OrderResult(success=False, error="Order not found")
            if order.status.is_terminal:
                return OrderResult(success=False, error="Order already final")

            if cancel_fn is not None:
                try:
                    if not cancel_fn(order_id):
                        return OrderResult(success=False, error="Broker cancel failed")
                except Exception as exc:
                    return OrderResult(success=False, error=str(exc))

            old_status = order.status
            updated = order.with_status(OrderStatus.CANCELLED)
            store_order(orders, orders_by_correlation, updated)

            self._audit_logger.log_state_change(
                order_id,
                old_status,
                OrderStatus.CANCELLED,
                details={"reason": "User requested"},
            )
            if self._active_orders is not None:
                self._active_orders.dec()

            self._publish(EventType.ORDER_CANCELLED.value, updated)
            return OrderResult(success=True, order=updated)

    def modify_order(
        self,
        lock: threading.RLock,
        orders: dict[str, Order],
        orders_by_correlation: dict[str, Order],
        request: object,
        modify_fn: Callable[..., object] | None = None,
    ) -> OrderResult:
        """Modify a pending order locally and optionally at the broker."""
        from application.oms.order_manager import OrderResult
        from domain.orders.requests import ModifyOrderRequest

        req = request if isinstance(request, ModifyOrderRequest) else ModifyOrderRequest(
            order_id=getattr(request, "order_id", ""),
            quantity=getattr(request, "quantity", None),
            price=getattr(request, "price", None),
            order_type=getattr(request, "order_type", None),
            product_type=getattr(request, "product_type", None),
        )
        with lock:
            order = orders.get(req.order_id)
            if order is None:
                return OrderResult(success=False, error="Order not found")
            if order.status.is_terminal:
                return OrderResult(success=False, error="Order already final")

        # Kill-switch / risk guard (shared RiskManager owns the switch).
        if self._risk_manager is not None and self._risk_manager.is_kill_switch_active():
            return OrderResult(
                success=False,
                error=f"Order blocked: kill switch active (modify_order {req.order_id})",
            )

        if modify_fn is not None:
            try:
                response = modify_fn(req)
                if response is not None and not getattr(response, "success", True):
                    return OrderResult(
                        success=False,
                        error=getattr(response, "message", None)
                        or getattr(response, "error", "broker modify failed"),
                    )
            except Exception as exc:
                return OrderResult(success=False, error=str(exc))

        updated = apply_modify_fields(order, req)
        with lock:
            store_order(orders, orders_by_correlation, updated)
        self._publish(EventType.ORDER_UPDATED.value, updated)
        return OrderResult(success=True, order=updated)
