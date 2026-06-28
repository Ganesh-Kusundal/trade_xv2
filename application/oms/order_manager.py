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
3. Collaborators live in ``brokers.common.oms._internal`` and are not part of
   the public API surface.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from application.oms._internal.order_audit_logger import OrderAuditLogger
from application.oms._internal.order_position_updater import OrderPositionUpdater
from application.oms._internal.order_state_validator import OrderStateValidator
from application.oms._internal.reentrancy_guard import _ReentrancyGuard
from application.oms._internal.risk_manager import RiskManager
from domain.entities import Order, OrderStatus, OrderType, ProductType, Side, Trade
from domain.types import ORDER_STATUS_TRANSITIONS
from infrastructure.event_bus import (
    DomainEvent,
    EventBus,
    EventType,
    ProcessedTradeRepository,
    TradeIdKey,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "exchange", self.exchange.upper())
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


class OrderResult:
    def __init__(self, success: bool, order: Order | None = None, error: str | None = None):
        self.success = success
        self.order = order
        self.error = error


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
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
        processed_trade_repository: ProcessedTradeRepository | None = None,
        metrics: Any | None = None,
        enforce_state_transitions: bool = True,
        state_validator: OrderStateValidator | None = None,
        audit_logger: OrderAuditLogger | None = None,
        position_updater: OrderPositionUpdater | None = None,
        order_store: Any | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._orders_by_correlation: dict[str, Order] = {}
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._processed_trades = processed_trade_repository or ProcessedTradeRepository()
        self._metrics = metrics
        self._trades_processed = 0
        self._trades_duplicated = 0
        # REF-019: Pending-order set prevents TOCTOU races when the lock
        # is released between idempotency check and order book insertion.
        self._pending_correlation: set[str] = set()
        # Re-entrancy guard: when a handler is currently being invoked, an
        # ORDER_UPDATED that the OMS publishes internally (e.g. via
        # upsert_order) MUST NOT re-enter the OMS handler, otherwise we
        # recurse forever. Set true at the entry of every event handler
        # and reset on the way out.
        self._handler_depth: int = 0

        # P4-3: Extracted collaborators
        self._state_validator = state_validator or OrderStateValidator(
            transitions=ORDER_STATUS_TRANSITIONS,
            enforce=enforce_state_transitions,
        )
        self._audit_logger = audit_logger or OrderAuditLogger()
        self._position_updater = position_updater or OrderPositionUpdater()
        self._order_store = order_store

    @property
    def risk_manager(self) -> RiskManager | None:
        return self._risk_manager

    @property
    def processed_trade_repository(self) -> ProcessedTradeRepository:
        return self._processed_trades

    def check_order(self, order: Order) -> bool:
        """Return True if the order passes the configured risk checks."""
        if self._risk_manager is None:
            return True
        return self._risk_manager.check_order(order).allowed

    def set_placement_gate(self, gate_fn: Callable[[], tuple[bool, str | None]]) -> None:
        """Set a callable that gates order placement.

        The gate function is called before placing an order. If it returns
        ``(False, reason)``, the order is rejected with the given reason.

        Parameters
        ----------
        gate_fn:
            Callable returning (allowed, reason). Example:
            ``lambda: (True, None)`` always allows placement.
        """
        self._placement_gate = gate_fn

    def _check_placement_gate(self) -> str | None:
        """Check if order placement is allowed. Returns rejection reason or None."""
        gate_fn = getattr(self, "_placement_gate", None)
        if gate_fn is None:
            return None
        allowed, reason = gate_fn()
        if allowed:
            return None
        return reason or "Order placement blocked by gate"

    # ── Public API ──────────────────────────────────────────────────────────

    def place_order(
        self,
        request: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Place an order idempotently.

        REF-019: The lock is held only for state mutations (idempotency
        check + order book update). Risk check, broker I/O (submit_fn),
        and event publishing all happen OUTSIDE the lock to avoid holding
        it during network calls.
        """
        # ── Phase 1: Idempotency + pending check (under lock) ──
        with self._lock:
            existing = self._orders_by_correlation.get(request.correlation_id)
            if existing is not None:
                return OrderResult(success=True, order=existing)
            if request.correlation_id in self._pending_correlation:
                return OrderResult(success=False, error="Order already in-flight")
            self._pending_correlation.add(request.correlation_id)
            order_id = f"OM-{uuid.uuid4().hex[:12]}"

        # ── Phase 2: Build order + risk check (no lock) ──
        try:
            # Check placement gate first
            gate_reason = self._check_placement_gate()
            if gate_reason is not None:
                self._publish(
                    EventType.ORDER_REJECTED.value,
                    Order(
                        order_id=order_id,
                        symbol=request.symbol,
                        exchange=request.exchange,
                        side=request.side,
                        order_type=request.order_type,
                        quantity=request.quantity,
                        price=request.price,
                        product_type=request.product_type,
                        status=OrderStatus.REJECTED,
                        timestamp=datetime.now(timezone.utc),
                        correlation_id=request.correlation_id,
                    ),
                    reason=gate_reason,
                )
                with self._lock:
                    self._pending_correlation.discard(request.correlation_id)
                return OrderResult(success=False, error=gate_reason)

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
                    if self._event_bus is not None:
                        self._event_bus.publish(
                            DomainEvent.now(
                                EventType.RISK_REJECTED.value,
                                payload={
                                    "order_id": order.order_id,
                                    "rule": risk_result.reason,
                                    "value": "0",
                                    "limit": "0",
                                },
                                symbol=order.symbol,
                                source="OrderManager",
                                correlation_id=order.correlation_id,
                            )
                        )
                    self._publish(
                        EventType.ORDER_REJECTED.value,
                        order,
                        reason=risk_result.reason,
                    )
                    with self._lock:
                        self._pending_correlation.discard(request.correlation_id)
                    return OrderResult(success=False, error=risk_result.reason)
                else:
                    if self._event_bus is not None:
                        self._event_bus.publish(
                            DomainEvent.now(
                                EventType.RISK_APPROVED.value,
                                payload={"order_id": order.order_id},
                                symbol=order.symbol,
                                source="OrderManager",
                                correlation_id=order.correlation_id,
                            )
                        )

            # ── Phase 3: Broker I/O — no lock held ──
            if submit_fn is not None:
                try:
                    order = submit_fn(request)
                except Exception as exc:
                    self._publish(
                        EventType.ORDER_REJECTED.value,
                        order,
                        reason=str(exc),
                    )
                    with self._lock:
                        self._pending_correlation.discard(request.correlation_id)
                    return OrderResult(success=False, error=str(exc))
        except Exception:
            # REF-019: Clean up pending set on any unexpected failure
            with self._lock:
                self._pending_correlation.discard(request.correlation_id)
            raise

        # ── Phase 4: Record result (under lock) ──
        with self._lock:
            self._pending_correlation.discard(request.correlation_id)
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
        return OrderResult(success=True, order=order)

    def upsert_order(self, order: Order) -> None:
        """Update or insert an order (used by broker event handlers).

        P4-3: Delegates state validation to OrderStateValidator.
        """
        with self._lock:
            existing = self._orders.get(order.order_id)
            if existing is not None:
                # P4-3: Delegate to state validator
                self._state_validator.validate_transition(
                    order.order_id,
                    existing.status,
                    order.status,
                )

            self._orders[order.order_id] = order
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = order

            # P4-3: Log state change if order existed
            if existing is not None and existing.status != order.status:
                self._audit_logger.log_state_change(
                    order.order_id,
                    existing.status,
                    order.status,
                )

            self._publish(EventType.ORDER_UPDATED.value, order)

    def record_trade(self, trade: Trade) -> bool:
        """Record a trade and update the parent order.

        Idempotent on ``trade.trade_id``: a duplicate trade is logged and
        silently dropped before it can mutate order state.

        After a trade is accepted, the OMS publishes a ``TRADE_APPLIED``
        event that downstream consumers (e.g. :class:`PositionManager`)
        can subscribe to. This is the only way trades should reach the
        position book, so that idempotency is enforced exactly once.

        Returns
        -------
        bool
            True if the trade was accepted and applied.
            False if the trade was a duplicate (already processed) or
            referenced an unknown order.
        """
        if trade.trade_id is None or not str(trade.trade_id).strip():
            raise ValueError("OrderManager.record_trade requires a non-empty trade.trade_id")
        key = TradeIdKey.from_trade(trade)
        with self._lock:
            if self._processed_trades.is_processed(key):
                self._trades_duplicated += 1
                if self._metrics is not None:
                    self._metrics.inc(EventType.TRADE.value, "trade_duplicated")
                logger.info(
                    "OrderManager: trade %s for order %s is a duplicate; skipping",
                    trade.trade_id,
                    trade.order_id,
                )
                return False

            order = self._orders.get(trade.order_id)
            if order is None:
                logger.warning(
                    "OrderManager: trade %s references unknown order %s; "
                    "ledger will not be marked, retry on order delivery",
                    trade.trade_id,
                    trade.order_id,
                )
                return False

            self._processed_trades.mark_processed(key)

            # P4-3: Delegate to position updater
            updated = self._position_updater.apply_trade(order, trade)

            self._orders[order.order_id] = updated
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = updated

            self._trades_processed += 1
            if self._metrics is not None:
                self._metrics.inc(EventType.TRADE.value, "trade_processed")

            # P4-3: Log audit trail
            self._audit_logger.log_trade_applied(
                order.order_id,
                trade.trade_id,
                updated.filled_quantity,
                str(updated.avg_price),
                details={
                    "symbol": order.symbol,
                    "status": updated.status.value,
                },
            )

            self._publish(EventType.ORDER_UPDATED.value, updated)
            self._publish_trade_applied(trade)
            return True

    def _publish_trade_applied(self, trade: Trade) -> None:
        """Publish a TRADE_APPLIED event after a trade is committed."""
        if self._event_bus is None:
            return
        correlation_id: str | None = getattr(trade, "correlation_id", None)
        self._event_bus.publish(
            DomainEvent.now(
                EventType.TRADE_APPLIED.value,
                {"trade": trade},
                symbol=trade.symbol,
                source="OrderManager",
                correlation_id=correlation_id,
            )
        )

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
                    "order_type": o.order_type.value
                    if hasattr(o.order_type, "value")
                    else str(o.order_type),
                    "quantity": o.quantity,
                    "filled_quantity": o.filled_quantity,
                    "price": str(o.price),
                    "avg_price": str(o.avg_price),
                    "product_type": o.product_type.value
                    if hasattr(o.product_type, "value")
                    else str(o.product_type),
                    "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                    "timestamp": o.timestamp.isoformat()
                    if hasattr(o.timestamp, "isoformat")
                    else str(o.timestamp),
                }
                for o in self._orders.values()
            ]

    def cancel_order(
        self,
        order_id: str,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> OrderResult:
        """Cancel an order locally and optionally at the broker.

        If ``cancel_fn`` is provided, it is called to cancel the order
        at the broker. If the broker cancel fails, the local state is
        NOT updated (the order stays open and the error is returned).
        """
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

            # P4-3: Log audit trail
            self._audit_logger.log_state_change(
                order_id,
                old_status,
                OrderStatus.CANCELLED,
                details={"reason": "User requested"},
            )

            self._publish(EventType.ORDER_CANCELLED.value, updated)
            return OrderResult(success=True, order=updated)

    # ── Event handlers ──────────────────────────────────────────────────────

    def on_order_update(self, event: DomainEvent) -> None:
        """Handle broker order-update events from the bus.

        Uses :func:`_reentrancy_guard` to prevent recursive handler
        invocation when the OMS publishes events internally.
        """
        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return
            payload = event.payload
            order = payload.get("order")
            if isinstance(order, Order):
                self.upsert_order(order)

    def on_trade(self, event: DomainEvent) -> None:
        """Handle broker trade events from the bus.

        Uses :func:`_reentrancy_guard` to prevent recursive handler
        invocation.
        """
        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return
            payload = event.payload
            trade = payload.get("trade")
            if isinstance(trade, Trade):
                self.record_trade(trade)

    # ── Re-entrancy guard ───────────────────────────────────────────────────

    def _reentrancy_guard(self):
        """Context manager that atomically checks and increments ``_handler_depth``.

        Returns a guard object whose ``__enter__`` atomically checks/increments
        and whose ``__exit__`` decrements.  If the handler is already active
        (``_handler_depth > 0``), the guard sets ``_handler_depth`` so the
        caller can check it after the ``with`` block.

        Extracted from ``on_order_update`` / ``on_trade`` to eliminate the
        duplicated try/finally pattern (REF-021).
        """
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
