"""Central order management system.

Single owner for order state. All order placement, updates, and queries go
through this manager. It is protected by one ``threading.RLock`` and uses
immutable ``Order`` / ``Trade`` value objects.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from brokers.common.core.domain import Order, OrderStatus, OrderType, ProductType, Side, Trade
from brokers.common.core.state_machine import IllegalTransitionError, StateMachine
from brokers.common.core.types import ORDER_STATUS_TRANSITIONS
from brokers.common.event_bus import (
    DomainEvent,
    EventBus,
    EventType,
    ProcessedTradeRepository,
    TradeIdKey,
)
from brokers.common.oms.risk_manager import RiskManager

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
            object.__setattr__(self, "correlation_id", f"ord:{uuid.uuid4().hex[:12]}")


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
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
        processed_trade_repository: ProcessedTradeRepository | None = None,
        metrics: Any | None = None,
        enforce_state_transitions: bool = False,  # P2-Phase 2: Audit-only by default
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
        # Re-entrancy guard: when a handler is currently being invoked, an
        # ORDER_UPDATED that the OMS publishes internally (e.g. via
        # upsert_order) MUST NOT re-enter the OMS handler, otherwise we
        # recurse forever. Set true at the entry of every event handler
        # and reset on the way out.
        self._handler_depth: int = 0
        
        # P2-Phase 2: State machine enforcement (audit-only mode first)
        self._enforce_state_transitions = enforce_state_transitions
        self._state_machines: dict[str, StateMachine[OrderStatus]] = {}  # order_id -> StateMachine

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

    # ── Public API ──────────────────────────────────────────────────────────

    def place_order(
        self,
        request: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
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
                    # P1-Phase 1: Publish RISK_REJECTED alongside ORDER_REJECTED
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
                        EventType.ORDER_REJECTED.value, order,  # P1-3: Migrated to EventType enum
                        reason=risk_result.reason,
                    )
                    return OrderResult(success=False, error=risk_result.reason)
                else:
                    # P1-Phase 1: Publish RISK_APPROVED when risk check passes
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

            if submit_fn is not None:
                try:
                    order = submit_fn(request)
                except Exception as exc:
                    self._publish(
                        EventType.ORDER_REJECTED.value, order,  # P1-3: Migrated to EventType enum
                        reason=str(exc),
                    )
                    return OrderResult(success=False, error=str(exc))

            self._orders[order.order_id] = order
            self._orders_by_correlation[request.correlation_id] = order
            self._publish(EventType.ORDER_PLACED.value, order)  # P1-3: Migrated to EventType enum
            return OrderResult(success=True, order=order)

    def upsert_order(self, order: Order) -> None:
        """Update or insert an order (used by broker event handlers).
        
        P2-Phase 2: Validates order status transitions using state machine.
        In audit-only mode (default), logs violations but accepts the update.
        In enforcement mode, raises IllegalTransitionError on invalid transitions.
        """
        with self._lock:
            # P2-Phase 2: Validate state transition
            existing = self._orders.get(order.order_id)
            if existing is not None:
                # Order exists: validate transition
                old_status = existing.status
                new_status = order.status
                
                if old_status != new_status:
                    # Status changed: validate transition
                    state_machine = self._state_machines.get(order.order_id)
                    if state_machine is None:
                        # Create state machine from current status
                        state_machine = StateMachine(
                            transitions=ORDER_STATUS_TRANSITIONS,
                            initial=old_status,
                        )
                        self._state_machines[order.order_id] = state_machine
                    
                    if not state_machine.can_transition_to(new_status):
                        if self._enforce_state_transitions:
                            raise IllegalTransitionError(old_status, new_status)
                        else:
                            # Audit-only mode: log violation but accept
                            logger.warning(
                                "OrderManager: illegal order status transition "
                                "%s → %s for order %s (audit mode: accepting)",
                                old_status.value,
                                new_status.value,
                                order.order_id,
                            )
                    else:
                        # Valid transition: update state machine
                        state_machine.transition_to(new_status)
            else:
                # New order: create state machine
                state_machine = StateMachine(
                    transitions=ORDER_STATUS_TRANSITIONS,
                    initial=order.status,
                )
                self._state_machines[order.order_id] = state_machine
            
            self._orders[order.order_id] = order
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = order
            self._publish(EventType.ORDER_UPDATED.value, order)  # P1-3: Migrated to EventType enum

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

        Notes
        -----
        A trade for an unknown order is **not** marked in the ledger:
        a later delivery of the order event should be allowed to retry
        processing the trade.
        """
        if trade.trade_id is None or not str(trade.trade_id).strip():
            raise ValueError(
                "OrderManager.record_trade requires a non-empty trade.trade_id"
            )
        key = TradeIdKey.from_trade(trade)
        with self._lock:
            if self._processed_trades.is_processed(key):
                self._trades_duplicated += 1
                if self._metrics is not None:
                    self._metrics.inc(EventType.TRADE.value, "trade_duplicated")  # P1-3: Migrated to EventType enum
                logger.info(
                    "OrderManager: trade %s for order %s is a duplicate; skipping",
                    trade.trade_id,
                    trade.order_id,
                )
                return False

            order = self._orders.get(trade.order_id)
            if order is None:
                # Trade arrived before (or without) its order. Do NOT mark
                # the ledger, so that once the order surfaces we can
                # retry the trade by re-publishing the event.
                logger.warning(
                    "OrderManager: trade %s references unknown order %s; "
                    "ledger will not be marked, retry on order delivery",
                    trade.trade_id,
                    trade.order_id,
                )
                return False

            # Mark the ledger only after we have a known order — this
            # guarantees a transient order-event race does not silently
            # swallow a real trade.
            self._processed_trades.mark_processed(key)

            new_filled = order.filled_quantity + trade.quantity
            new_avg = self._compute_avg_price(order, trade)
            new_status = (
                OrderStatus.FILLED
                if new_filled >= order.quantity
                else OrderStatus.PARTIALLY_FILLED
            )
            updated = order.with_fill(new_filled, new_avg).with_status(new_status)
            self._orders[order.order_id] = updated
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = updated
            self._trades_processed += 1
            if self._metrics is not None:
                self._metrics.inc(EventType.TRADE.value, "trade_processed")  # P1-3: Migrated to EventType enum
            self._publish(EventType.ORDER_UPDATED.value, updated)  # P1-3: Migrated to EventType enum
            # Downstream event consumed by PositionManager. The OMS is the
            # sole gatekeeper for trade idempotency; downstream consumers
            # must subscribe here, NOT to raw TRADE events, to avoid
            # double-counting duplicates.
            self._publish_trade_applied(trade)
            return True

    def _publish_trade_applied(self, trade: Trade) -> None:
        """Publish a TRADE_APPLIED event after a trade is committed."""
        if self._event_bus is None:
            return
        correlation_id: str | None = getattr(trade, "correlation_id", None)
        self._event_bus.publish(
            DomainEvent.now(
                EventType.TRADE_APPLIED.value,  # P1-3: Migrated to EventType enum
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

            updated = order.with_status(OrderStatus.CANCELLED)
            self._orders[order_id] = updated
            if order.correlation_id:
                self._orders_by_correlation[order.correlation_id] = updated
            self._publish(EventType.ORDER_CANCELLED.value, updated)  # P1-3: Migrated to EventType enum
            return OrderResult(success=True, order=updated)

    # ── Event handlers ──────────────────────────────────────────────────────

    def on_order_update(self, event: DomainEvent) -> None:
        """Handle broker order-update events from the bus.

        Re-entrancy: if we are already inside an OMS handler, the
        ORDER_UPDATED events that the OMS itself publishes (e.g. via
        :meth:`upsert_order` or :meth:`record_trade`) must NOT re-enter
        this handler. Otherwise a single external ORDER_UPDATED triggers
        an infinite publish→handle→publish loop.

        Thread-safe: the depth check/increment is inside ``_lock`` so
        concurrent threads cannot race on ``_handler_depth`` and
        permanently disable the handler.
        """
        with self._lock:
            if self._handler_depth > 0:
                return
            self._handler_depth += 1
        try:
            payload = event.payload
            order = payload.get("order")
            if isinstance(order, Order):
                self.upsert_order(order)
        finally:
            with self._lock:
                self._handler_depth -= 1

    def on_trade(self, event: DomainEvent) -> None:
        """Handle broker trade events from the bus.

        Idempotent: duplicates are dropped silently (counted in metrics
        and the ledger) before any state mutation.

        Thread-safe: the depth guard is inside ``_lock`` (see
        :meth:`on_order_update`).
        """
        with self._lock:
            if self._handler_depth > 0:
                return
            self._handler_depth += 1
        try:
            payload = event.payload
            trade = payload.get("trade")
            if isinstance(trade, Trade):
                self.record_trade(trade)
        finally:
            with self._lock:
                self._handler_depth -= 1

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _publish(
        self, event_type: str, obj: Order | Trade,
        *, reason: str | None = None,
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
                event_type, payload,
                symbol=symbol,
                source="OrderManager",
                correlation_id=correlation_id,
            )
        )

    @staticmethod
    def _compute_avg_price(order: Order, trade: Trade) -> Decimal:
        if order.filled_quantity == 0:
            return trade.price
        total_value = order.avg_price * Decimal(order.filled_quantity) + trade.price * Decimal(trade.quantity)
        total_qty = order.filled_quantity + trade.quantity
        return total_value / Decimal(total_qty) if total_qty else Decimal("0")
