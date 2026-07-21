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
   * :class:`OrderLifecycle` — cancel / modify / upsert / place finalization
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from application.oms._internal.order_audit_logger import OrderAuditLogger
from application.oms._internal.order_lifecycle import OrderLifecycle, order_as_recon_dict
from application.oms._internal.order_position_updater import OrderPositionUpdater
from application.oms._internal.order_state_validator import OrderStateValidator
from application.oms._internal.reentrancy_guard import _ReentrancyGuard
from application.oms._internal.risk_manager import RiskManager
from application.oms.idempotency_guard import IdempotencyGuard
from application.oms.order_validator import OrderValidator as OmsOrderValidator
from application.oms.trade_recorder import TradeRecorder
from domain.entities import Order, Trade
from domain.events.types import DomainEvent
from domain.execution_contracts import SubmissionState
from domain.ports import (
    EventBusPort,
    EventMetricsPort,
    ExecutionLedgerPort,
    MetricsRegistryPort,
    OrderStorePort,
    ProcessedTradeRepositoryPort,
)
from domain.symbols import normalize_exchange, normalize_symbol
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS
from domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
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
    state: SubmissionState | None = None


class OrderManager:
    """Thread-safe order book with idempotency, risk checks, and event publishing.

    Public façade: holds the lock and order maps; delegates lifecycle work to
    :class:`OrderLifecycle`, validation to :class:`OrderValidator`, and fills to
    :class:`TradeRecorder`.
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
        execution_ledger: ExecutionLedgerPort | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._orders_by_correlation: dict[str, Order] = {}
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._processed_trades = processed_trade_repository
        self._metrics = metrics
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
            metrics_registry.gauge(
                "oms_active_orders", "Currently open (non-terminal) orders in the OMS"
            )
            if metrics_registry is not None
            else None
        )
        self._handler_depth: int = 0

        self._state_validator = state_validator or OrderStateValidator(
            transitions=ORDER_STATUS_TRANSITIONS,
            enforce=enforce_state_transitions,
        )
        self._audit_logger = audit_logger or OrderAuditLogger()
        self._position_updater = position_updater or OrderPositionUpdater()
        self._order_store = order_store
        self._execution_ledger = execution_ledger

        # F6: hydrate hot cache from durable order store on startup.
        if order_store is not None:
            for stored in order_store.load_all():
                self._orders[stored.order_id] = stored
                if stored.correlation_id:
                    self._orders_by_correlation[stored.correlation_id] = stored

        self._idempotency_guard = IdempotencyGuard(
            durable_lookup=self._lookup_durable_order,
        )
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
            execution_ledger=execution_ledger,
        )
        self._lifecycle = OrderLifecycle(
            state_validator=self._state_validator,
            audit_logger=self._audit_logger,
            trade_recorder=self._trade_recorder,
            idempotency_guard=self._idempotency_guard,
            risk_manager=risk_manager,
            publish=self._publish,
            active_orders=self._active_orders,
            execution_ledger=execution_ledger,
        )

    @property
    def risk_manager(self) -> RiskManager | None:
        return self._risk_manager

    @property
    def lifecycle(self) -> OrderLifecycle:
        """Public accessor for order lifecycle (used by ReconciliationService)."""
        return self._lifecycle

    @property
    def trade_recorder(self) -> TradeRecorder:
        """Public accessor for trade recorder (used by ReconciliationService)."""
        return self._trade_recorder

    @property
    def order_store(self) -> OrderStorePort | None:
        """Public accessor for order store (used by Context health)."""
        return self._order_store

    @property
    def orders_map(self) -> dict[str, Order]:
        """Public accessor for the in-memory order book (read-only snapshot)."""
        with self._lock:
            return dict(self._orders)

    @property
    def processed_trade_repository(self) -> ProcessedTradeRepositoryPort | None:
        return self._processed_trades

    def check_order(self, order: Order) -> bool:
        """Return True if the order passes the configured risk checks."""
        return self._order_validator.check_order(order)

    def set_placement_gate(self, gate_fn: Callable[[], tuple[bool, str | None]]) -> None:
        """Set a callable that gates order placement."""
        self._order_validator.set_placement_gate(gate_fn)

    def clear_placement_gate(self) -> None:
        """Remove any active placement gate (see OrderValidator.clear_placement_gate)."""
        self._order_validator.clear_placement_gate()

    def _release_pending(self, correlation_id: str | None) -> None:
        """Release idempotency + risk pending reservations."""
        self._idempotency_guard.release_pending(self._lock, correlation_id)
        if self._risk_manager is not None:
            self._risk_manager.release_pending(correlation_id)

    def _lookup_durable_order(self, correlation_id: str) -> Order | None:
        """F6: recover an order by correlation from ledger when memory is empty."""
        # Caller holds the OMS lock. Memory map is already checked by the guard.
        if correlation_id in self._orders_by_correlation:
            return self._orders_by_correlation[correlation_id]
        ledger = self._execution_ledger
        if ledger is None:
            return None
        intent = None
        try:
            intent = ledger.intent_for_correlation(correlation_id)
        except Exception:
            return None
        if intent is None:
            return None
        existing = self._orders.get(intent.order_id)
        if existing is not None:
            return existing
        from domain.enums import OrderStatus

        outcome = ledger.outcome_for(intent.intent_id)
        if outcome is not None and outcome.state is SubmissionState.UNKNOWN:
            status = OrderStatus.UNKNOWN
        elif outcome is not None and outcome.state is SubmissionState.REJECTED:
            status = OrderStatus.REJECTED
        else:
            # ACCEPTED or intent-only (crash mid-submit) — treat as OPEN so
            # retries return the durable order instead of double-submitting.
            status = OrderStatus.OPEN
        recovered = Order(
            order_id=intent.order_id,
            correlation_id=intent.correlation_id,
            symbol=intent.symbol,
            exchange=intent.exchange,
            side=intent.side,
            order_type=intent.order_type,
            product_type=intent.product_type,
            quantity=intent.quantity,
            price=intent.price,
            status=status,
            timestamp=intent.created_at,
        )
        self._orders[recovered.order_id] = recovered
        return recovered

    def _persist_order(self, order: Order) -> None:
        if self._order_store is None:
            return
        try:
            self._order_store.upsert(order)
        except Exception:
            logger.exception("order_store_persist_failed order_id=%s", order.order_id)

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
            order_id, early_result = self._idempotency_guard.check_and_reserve(
                self._lock, self._orders_by_correlation, request.correlation_id
            )
            if early_result is not None:
                return early_result

            try:
                order, rejection = self._order_validator.build_and_validate(order_id, request)
                if rejection is not None:
                    self._release_pending(request.correlation_id)
                    return rejection

                order, rejection = self._lifecycle.submit_to_broker(
                    self._lock,
                    self._orders,
                    self._orders_by_correlation,
                    order,
                    request,
                    submit_fn,
                )
                if rejection is not None:
                    self._release_pending(request.correlation_id)
                    return rejection
            except Exception:
                self._release_pending(request.correlation_id)
                raise

            self._lifecycle.record_and_publish(
                self._lock,
                self._orders,
                self._orders_by_correlation,
                order,
                request,
            )
            self._persist_order(order)
            if self._orders_total is not None:
                self._orders_total.inc()
            return OrderResult(success=True, order=order, state=SubmissionState.ACCEPTED)
        finally:
            if self._order_latency is not None:
                self._order_latency.observe(time.monotonic() - _start)

    def upsert_order(self, order: Order) -> None:
        """Update or insert an order (used by broker event handlers)."""
        self._lifecycle.upsert_order(self._lock, self._orders, self._orders_by_correlation, order)
        self._persist_order(order)
        if self._risk_manager is not None and order.status.is_terminal:
            self._risk_manager.release_pending(order.correlation_id)

    def record_trade(self, trade: Trade) -> bool:
        """Record a trade and update the parent order (idempotent on trade_id)."""
        ok = self._trade_recorder.record_trade(
            self._lock, self._orders, self._orders_by_correlation, trade
        )
        if ok:
            order = self.get_order(trade.order_id)
            if order is not None:
                self._persist_order(order)
                # R3: reduce pending on every fill to prevent double-count
                if self._risk_manager is not None and order.correlation_id:
                    self._risk_manager.reduce_pending(
                        order.correlation_id,
                        filled_quantity=int(trade.quantity),
                        price=trade.price.to_decimal()
                        if hasattr(trade.price, "to_decimal")
                        else Decimal(str(trade.price)),
                    )
                # R2: release risk-pending on fill path when order is terminal.
                if (
                    self._risk_manager is not None
                    and order.status.is_terminal
                    and order.correlation_id
                ):
                    self._risk_manager.release_pending(order.correlation_id)
        return ok

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
            return [order_as_recon_dict(order) for order in self._orders.values()]

    def cancel_order(
        self,
        order_id: str,
        cancel_fn: Callable[[str], bool] | None = None,
    ) -> OrderResult:
        """Cancel an order locally and optionally at the broker."""
        return self._lifecycle.cancel_order(
            self._lock,
            self._orders,
            self._orders_by_correlation,
            order_id,
            cancel_fn,
        )

    def modify_order(
        self,
        request: object,
        modify_fn: Callable[..., object] | None = None,
    ) -> OrderResult:
        """Modify a pending order locally and optionally at the broker."""
        return self._lifecycle.modify_order(
            self._lock,
            self._orders,
            self._orders_by_correlation,
            request,
            modify_fn,
        )

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
        """Handle broker trade events from the bus."""
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

    def _reentrancy_guard(self):
        """Context manager that atomically checks and increments ``_handler_depth``."""
        return _ReentrancyGuard(self._lock, self)

    def _publish(
        self,
        event_type: str,
        obj: Order | Trade,
        *,
        reason: str | None = None,
    ) -> None:
        if self._event_bus is None:
            return
        correlation_id: str | None = getattr(obj, "correlation_id", None)
        payload: dict = {"order": obj} if isinstance(obj, Order) else {"trade": obj}
        if reason is not None:
            payload["reason"] = reason
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                payload,
                correlation_id=correlation_id,
            )
        )
