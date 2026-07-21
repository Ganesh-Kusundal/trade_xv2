"""Order book lifecycle ops extracted from OrderManager.

Owns cancel / modify / upsert / place finalization against the in-memory
order maps.  OrderManager remains the public façade and lock owner.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from application.oms._internal.order_mutation_guard import OrderMutationGuard
from domain.events.types import EventType
from domain.execution_contracts import OrderIntent, SubmissionOutcome, SubmissionState
from domain.ports.time_service import ClockPort, get_current_clock
from domain.enums import OrderStatus

if TYPE_CHECKING:
    from application.oms._internal.order_audit_logger import OrderAuditLogger
    from application.oms._internal.order_state_validator import OrderStateValidator
    from application.oms._internal.risk_manager import RiskManager
    from application.oms.idempotency_guard import IdempotencyGuard
    from application.oms.order_manager import OmsOrderCommand, OrderResult
    from application.oms.trade_recorder import TradeRecorder
    from domain.entities import Order
    from domain.ports import ExecutionLedgerPort


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
        execution_ledger: ExecutionLedgerPort | None = None,
        clock: ClockPort | None = None,
    ) -> None:
        self._state_validator = state_validator
        self._audit_logger = audit_logger
        self._trade_recorder = trade_recorder
        self._idempotency_guard = idempotency_guard
        self._risk_manager = risk_manager
        self._publish = publish
        self._active_orders = active_orders
        self._execution_ledger = execution_ledger
        self._clock = clock or get_current_clock()
        self._mutation_guard = OrderMutationGuard(risk_manager)

    def _guard_mutation(self, action: str) -> OrderResult | None:
        """Return OrderResult on kill-switch block, else None."""
        from application.oms.order_manager import OrderResult

        guard = self._mutation_guard.check(action)  # type: ignore[arg-type]
        if guard.allowed:
            return None
        return OrderResult(success=False, error=guard.reason)

    @property
    def execution_ledger(self) -> ExecutionLedgerPort | None:
        """Public accessor for the execution ledger (used by ReconciliationService)."""
        return self._execution_ledger

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

        blocked = self._guard_mutation("place")
        if blocked is not None:
            return None, blocked

        if submit_fn is None:
            return order, None
        intent: OrderIntent | None = None
        if self._execution_ledger is not None:
            intent = OrderIntent(
                intent_id=order.order_id,
                order_id=order.order_id,
                correlation_id=request.correlation_id,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
                order_type=order.order_type,
                product_type=order.product_type,
                created_at=order.timestamp or self._clock.now(),
            )
            assert intent is not None
        # Record-then-submit: persist stub before broker I/O so a crash after
        # broker accept still leaves a reconcilable order in the book.
        with lock:
            orders[order.order_id] = order
            orders_by_correlation[request.correlation_id] = order

        def _broker_submit() -> Order:
            return submit_fn(request)

        try:
            if intent is not None and self._execution_ledger is not None:
                # Record-then-submit: persist intent durably before broker I/O
                # so a crash after broker accept still leaves a reconcilable order.
                self._execution_ledger.record_intent(intent)
                order = _broker_submit()
            else:
                from application.oms.ledger_authority import (
                    ledger_authority_enabled,
                    require_execution_ledger,
                )

                if ledger_authority_enabled():
                    require_execution_ledger(None)
                order = _broker_submit()
        except Exception as exc:
            unknown = order.with_status(OrderStatus.UNKNOWN)
            with lock:
                orders[unknown.order_id] = unknown
                orders_by_correlation[request.correlation_id] = unknown
            if self._execution_ledger is not None:
                self._execution_ledger.record_outcome(
                    SubmissionOutcome.unknown(
                        intent.intent_id if intent is not None else order.order_id,
                        str(exc),
                    )
                )
            self._publish(
                EventType.ORDER_UPDATED.value,
                unknown,
                reason=str(exc),
            )
            return None, OrderResult(
                success=False,
                order=unknown,
                error=str(exc),
                state=SubmissionState.UNKNOWN,
            )

        if self._execution_ledger is not None:
            try:
                self._execution_ledger.record_outcome(
                    SubmissionOutcome.accepted(
                        intent.intent_id if intent is not None else order.order_id,
                        order.order_id,
                    )
                )
            except Exception as exc:
                unknown = order.with_status(OrderStatus.UNKNOWN)
                with lock:
                    orders[unknown.order_id] = unknown
                    orders_by_correlation[request.correlation_id] = unknown
                self._publish(
                    EventType.ORDER_UPDATED.value,
                    unknown,
                    reason=f"accepted broker order could not be durably recorded: {exc}",
                )
                return None, OrderResult(
                    success=False,
                    order=unknown,
                    error=f"accepted broker order could not be durably recorded: {exc}",
                    state=SubmissionState.UNKNOWN,
                )
        return order, None

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
            if existing is not None and existing.status != order.status:
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

        blocked = self._guard_mutation("cancel")
        if blocked is not None:
            return blocked

        if cancel_fn is not None:
            try:
                if not cancel_fn(order_id):
                    return OrderResult(success=False, error="Broker cancel failed")
            except Exception as exc:
                return OrderResult(success=False, error=str(exc))

        with lock:
            order = orders.get(order_id)
            if order is None:
                return OrderResult(success=False, error="Order not found")
            if order.status.is_terminal:
                return OrderResult(success=False, error="Order already final")

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

        req = (
            request
            if isinstance(request, ModifyOrderRequest)
            else ModifyOrderRequest(
                order_id=getattr(request, "order_id", ""),
                quantity=getattr(request, "quantity", None),
                price=getattr(request, "price", None),
                order_type=getattr(request, "order_type", None),
                product_type=getattr(request, "product_type", None),
            )
        )
        with lock:
            order = orders.get(req.order_id)
            if order is None:
                return OrderResult(success=False, error="Order not found")
            if order.status.is_terminal:
                return OrderResult(success=False, error="Order already final")

        blocked = self._guard_mutation("modify")
        if blocked is not None:
            return blocked

        if modify_fn is not None:
            try:
                response = modify_fn(req)
                if response is not None and not getattr(response, "success", False):
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
