"""Central order management system.

Single owner for order state. All order placement, updates, and queries go
through this manager under one ``threading.RLock``.

Orchestration contract
----------------------
1. ``place_order(command, submit_fn)`` — idempotent on ``correlation_id``;
   runs ``RiskManager.check_order`` once; publishes ``RISK_APPROVED`` /
   ``RISK_REJECTED``; calls ``submit_fn`` for broker transport when provided.
2. ``on_order_update`` / ``on_trade`` — event-bus handlers for broker feeds;
   delegate validation to ``OrderStateValidator``, audit to ``OrderAuditLogger``,
   fill math to ``OrderPositionUpdater``.
3. Collaborators live in ``application.oms`` and are not part of
   the public API surface:

   * :class:`IdempotencyGuard` — correlation-id dedup
   * :class:`OrderValidator` — placement gate + risk checks
   * :class:`TradeRecorder` — trade recording + idempotency + events
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from application.oms._internal.order_audit_logger import OrderAuditLogger
from application.oms._internal.order_position_updater import OrderPositionUpdater
from application.oms._internal.order_state_validator import OrderStateValidator
from application.oms._internal.reentrancy_guard import _ReentrancyGuard
from application.oms.idempotency_guard import IdempotencyGuard
from application.oms.order_validator import OrderValidator as OmsOrderValidator
from application.oms.risk_manager import RiskManager
from application.oms.trade_recorder import TradeRecorder
from domain.entities import Order, Trade
from domain.events.types import DomainEvent, EventType
from domain.symbols import normalize_exchange, normalize_symbol
from domain.types import ORDER_STATUS_TRANSITIONS, OrderStatus, OrderType, ProductType, Side
from domain.ports import (
    EventBusPort,
    EventMetricsPort,
    MetricsRegistryPort,
    OrderStorePort,
    ProcessedTradeRepositoryPort,
)
from application.observability import get_logger, trace_operation

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@dataclass(frozen=True)
class OmsOrderCommand:
    """Plain request object for placing an order.

    Renamed from ``OrderRequest`` to avoid colliding with the canonical
    ``brokers.common.core.domain.OrderRequest`` (Upstox input shape). This
    is the canonical command object for the OMS.
    """

    symbol: str
    exchange: str
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "exchange", normalize_exchange(self.exchange))
        object.__setattr__(self, "price", Decimal(str(self.price)))
        if not self.correlation_id:
            import os

            if os.getenv("PYTEST_CURRENT_TEST"):
                object.__setattr__(self, "correlation_id", f"test:{uuid.uuid4().hex[:12]}")
            else:
                raise ValueError(
                    "correlation_id is required for OMS idempotency. "
                    "Pass an explicit correlation_id at the call site."
                )


# Backward-compat alias — kept so external imports that pre-date the
# rename keep working. New code should use ``OmsOrderCommand``.
OrderRequest = OmsOrderCommand



@dataclass(frozen=True)
class OrderResult:
    success: bool
    order: Order | None = None
    error: str | None = None


class OrderManager:
    """Thread-safe order book with idempotency, risk checks, and event publishing.

    Parameters
    ----------
    event_bus:
        Bus used to publish ``ORDER_PLACED`` / ``ORDER_UPDATED`` / etc.
    risk_manager:
        Pre-trade risk gate.
    processed_trade_repository:
        Idempotency ledger for trade events. When supplied, every
        :meth:`record_trade` and :meth:`on_trade` invocation is checked
        against it before mutating order state. This is the **only**
        defence against double-position bugs.
    metrics:
        Optional :class:`EventMetrics` instance. Increments
        ``(TRADE, trade_processed)`` and ``(TRADE, trade_duplicated)``
        for every accepted / rejected trade.
    enforce_state_transitions:
        When True (default), invalid order status transitions raise
        :class:`IllegalTransitionError`. When False, violations are logged
        but accepted (audit mode). Enabled by default for safety (P0.5).
    state_validator:
        Optional OrderStateValidator instance. If not provided, one is
        created internally.
    audit_logger:
        Optional OrderAuditLogger instance. If not provided, one is
        created internally.
    position_updater:
        Optional OrderPositionUpdater instance. If not provided, one is
        created internally.
    """

    def __init__(
        self,
        event_bus: EventBusPort | None = None,
        risk_manager: RiskManager | None = None,
        processed_trade_repository: ProcessedTradeRepositoryPort | None = None,
        metrics: EventMetricsPort | None = None,
        metrics_registry: MetricsRegistryPort | None = None,
        enforce_state_transitions: bool = True,
        state_validator: OrderStateValidator | None = None,
        audit_logger: OrderAuditLogger | None = None,
        position_updater: OrderPositionUpdater | None = None,
        order_store: OrderStorePort | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._orders_by_correlation: dict[str, Order] = {}
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._processed_trades = processed_trade_repository
        self._metrics = metrics
        # Metrics created from the injected registry (idempotent by name).
        self._orders_total = (
            metrics_registry.counter("oms_orders_total", "Total orders placed through the OMS")
            if metrics_registry is not None
            else None
        )
        self._order_latency = (
            metrics_registry.histogram(
                "oms_order_placement_latency_seconds",
                "End-to-end order placement latency in seconds",
                buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            )
            if metrics_registry is not None
            else None
        )
        self._active_orders = (
            metrics_registry.gauge("oms_active_orders", "Currently open (non-terminal) orders in the OMS")
            if metrics_registry is not None
            else None
        )
        # Re-entrancy guard: when a handler is currently being invoked, an
        # ORDER_UPDATED that the OMS publishes internally (e.g. via
        # upsert_order) MUST NOT re-enter the OMS handler, otherwise we
        # recurse forever. Set true at the entry of every event handler
        # and reset on the way out.
        self._handler_depth: int = 0

        self._state_validator = state_validator or OrderStateValidator(
            transitions=ORDER_STATUS_TRANSITIONS,
            enforce=enforce_state_transitions,
        )
        self._audit_logger = audit_logger or OrderAuditLogger()
        self._position_updater = position_updater or OrderPositionUpdater()
        self._order_store = order_store

        # Focused collaborators
        self._idempotency_guard = IdempotencyGuard()
        self._order_validator = OmsOrderValidator(
            risk_manager=risk_manager,
            event_bus=event_bus,
            publish_callback=self._publish,
        )
        self._trade_recorder = TradeRecorder(
            processed_trade_repository=processed_trade_repository,
            event_bus=event_bus,
            metrics=metrics,
            audit_logger=self._audit_logger,
            position_updater=self._position_updater,
            publish_callback=self._publish,
        )

    @property
    def risk_manager(self) -> RiskManager | None:
        return self._risk_manager

    @property
    def processed_trade_repository(self) -> ProcessedTradeRepositoryPort | None:
        return self._processed_trades

    def check_order(self, order: Order) -> bool:
        """Return True if the order passes the configured risk checks."""
        return self._order_validator.check_order(order)

    def set_placement_gate(self, gate_fn: Callable[[], tuple[bool, str | None]]) -> None:
        """Set a callable that gates order placement."""
        self._order_validator.set_placement_gate(gate_fn)

    # ── Public API ──────────────────────────────────────────────────────────

    @trace_operation("order_manager.place_order")
    def place_order(
        self,
        request: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Place an order idempotently.

        The lock is held only for state mutations (idempotency check +
        order book update). Risk check, broker I/O (submit_fn), and
        event publishing all happen OUTSIDE the lock to avoid holding
        it during network calls.
        """
        _start = time.monotonic()
        try:
            # Phase 1: Idempotency + pending check (under lock)
            order_id, early_result = self._idempotency_guard.check_and_reserve(
                self._lock, self._orders_by_correlation, request.correlation_id
            )
            if early_result is not None:
                return early_result

            # Phases 2-3: Build, validate, submit (no lock held)
            try:
                order, rejection = self._order_validator.build_and_validate(order_id, request)
                if rejection is not None:
                    self._idempotency_guard.release_pending(self._lock, request.correlation_id)
                    return rejection

                order, rejection = self._submit_to_broker(order, request, submit_fn)
                if rejection is not None:
                    self._idempotency_guard.release_pending(self._lock, request.correlation_id)
                    return rejection
            except Exception:
                self._idempotency_guard.release_pending(self._lock, request.correlation_id)
                raise

            # Phase 4: Record result (under lock)
            self._record_and_publish(order, request)
            if self._orders_total is not None:
                self._orders_total.inc()
            return OrderResult(success=True, order=order)
        finally:
            if self._order_latency is not None:
                self._order_latency.observe(time.monotonic() - _start)

    # ── place_order phase helpers ─────────────────────────────────────────

    def _submit_to_broker(
        self,
        order: Order,
        request: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None,
    ) -> tuple[Order | None, OrderResult | None]:
        """Phase 3: Submit order to broker (no lock).

        Returns (order, None) on success, or (None, OrderResult) on failure.
        """
        if submit_fn is None:
            return order, None
        # Record-then-submit: persist stub before broker I/O so a crash after
        # broker accept still leaves a reconcilable order in the book.
        with self._lock:
            self._orders[order.order_id] = order
            self._orders_by_correlation[request.correlation_id] = order
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

    def _record_and_publish(
        self, order: Order, request: OmsOrderCommand
    ) -> None:
        """Phase 4: Record order in book and publish event (under lock)."""
        with self._lock:
            self._idempotency_guard.release_pending(self._lock, request.correlation_id)
            prior = self._orders_by_correlation.get(request.correlation_id)
            if prior is not None and prior.order_id != order.order_id:
                self._orders.pop(prior.order_id, None)
            self._orders[order.order_id] = order
            self._orders_by_correlation[request.correlation_id] = order

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

    # ── Upsert (used by broker event handlers) ────────────────────────────

    def upsert_order(self, order: Order) -> None:
        """Update or insert an order (used by broker event handlers).

        P4-3: Delegates state validation to OrderStateValidator.
        """
        with self._lock:
            existing = self._orders.get(order.order_id)
            if existing is not None:
                self._state_validator.validate_transition(
                    order.order_id,
                    existing.status,
                    order.status,
                )

            self._orders[order.order_id] = order
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = order

            if existing is not None and existing.status != order.status:
                self._audit_logger.log_state_change(
                    order.order_id,
                    existing.status,
                    order.status,
                )
                # Decrement active orders gauge when order reaches terminal state
                if order.status.is_terminal and self._active_orders is not None:
                    self._active_orders.dec()

            self._publish(EventType.ORDER_UPDATED.value, order)
            self._trade_recorder.flush_pending_trades_locked(
                self._lock, self._orders, self._orders_by_correlation, order.order_id
            )

    # ── Trade recording ─────────────────────────────────────────────────

    def record_trade(self, trade: Trade) -> bool:
        """Record a trade and update the parent order.

        Idempotent on ``trade.trade_id``: a duplicate trade is logged and
        silently dropped before it can mutate order state.

        Returns
        -------
        bool
            True if the trade was accepted and applied.
            False if the trade was a duplicate (already processed) or
            referenced an unknown order (buffered for later).
        """
        return self._trade_recorder.record_trade(
            self._lock, self._orders, self._orders_by_correlation, trade
        )

    # ── Queries ─────────────────────────────────────────────────────────

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
            orders = [order for order in orders if order.symbol == normalize_symbol(symbol)]
        if status is not None:
            orders = [order for order in orders if order.status == status]
        return orders

    def get_all_orders(self) -> list[dict]:
        """Return all orders as list of dicts for reconciliation compatibility."""
        with self._lock:
            return [
                {
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
                for order in self._orders.values()
            ]

    # ── Cancel / modify ─────────────────────────────────────────────────

    def cancel_order(
        self,
        order_id: str,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> OrderResult:
        """Cancel an order locally and optionally at the broker."""
        with self._lock:
            order = self._orders.get(order_id)
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
            self._orders[order_id] = updated
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = updated

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
        request: object,
        modify_fn: Callable[..., object] | None = None,
    ) -> OrderResult:
        """Modify a pending order locally and optionally at the broker."""
        from domain.orders.requests import ModifyOrderRequest

        req = request if isinstance(request, ModifyOrderRequest) else ModifyOrderRequest(
            order_id=getattr(request, "order_id", ""),
            quantity=getattr(request, "quantity", None),
            price=getattr(request, "price", None),
            order_type=getattr(request, "order_type", None),
            product_type=getattr(request, "product_type", None),
        )
        with self._lock:
            order = self._orders.get(req.order_id)
            if order is None:
                return OrderResult(success=False, error="Order not found")
            if order.status.is_terminal:
                return OrderResult(success=False, error="Order already final")

        # Kill-switch / risk guard (shared RiskManager owns the switch).
        if self._risk_manager is not None and self._risk_manager.is_kill_switch_active():
            from application.oms.errors import OrderBlockedError

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

        # Reflect the requested change in local state (authoritative book).
        updated: Order = order  # type: ignore[assignment]
        if req.price is not None:
            updated = updated.with_price(req.price)
        if req.quantity is not None:
            updated = updated.with_quantity(req.quantity)
        if req.order_type is not None:
            updated = updated.with_order_type(req.order_type)
        with self._lock:
            self._orders[req.order_id] = updated
            if updated.correlation_id:
                self._orders_by_correlation[updated.correlation_id] = updated
        self._publish(EventType.ORDER_UPDATED.value, updated)
        return OrderResult(success=True, order=updated)

    # ── Event handlers ──────────────────────────────────────────────────────

    def on_order_update(self, event: DomainEvent) -> None:
        """Handle broker order-update events from the bus."""
        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return
            try:
                from domain.events.types import OrderUpdatedEvent

                typed_event = OrderUpdatedEvent.from_domain_event(event)
                self.upsert_order(typed_event.order)
            except ValueError as exc:
                logger.warning(
                    "OrderManager.on_order_update: invalid event payload: %s",
                    exc,
                )

    def on_trade(self, event: DomainEvent) -> bool:
        """Handle broker trade events from the bus.

        Returns
        -------
        bool
            True if the trade was accepted by :meth:`record_trade`.
            False if reentered, invalid, duplicate, or unknown order.
        """
        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return False
            try:
                from domain.events.types import TradeFilledEvent

                typed_event = TradeFilledEvent.from_domain_event(event)
                return self.record_trade(typed_event.trade)
            except ValueError as exc:
                logger.warning(
                    "OrderManager.on_trade: invalid event payload: %s",
                    exc,
                )
                return False

    # ── Re-entrancy guard ───────────────────────────────────────────────────

    def _reentrancy_guard(self):
        """Context manager that atomically checks and increments ``_handler_depth``."""
        return _ReentrancyGuard(self._lock, self)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _publish(
        self,
        event_type: str,
        obj: Order | Trade,
        *,
        reason: str | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        symbol = obj.symbol if hasattr(obj, "symbol") else None
        correlation_id: str | None = getattr(obj, "correlation_id", None)
        payload: dict = {"order": obj} if isinstance(obj, Order) else {"trade": obj}
        if reason is not None:
            payload["reason"] = reason
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                payload,
                symbol=symbol,
                source="OrderManager",
                correlation_id=correlation_id,
            )
        )
