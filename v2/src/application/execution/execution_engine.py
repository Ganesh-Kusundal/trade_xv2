"""ExecutionEngine — single order spine: idempotency → risk → fill → OMS."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from application.execution.order_store import InMemoryOrderStore
from application.execution.protocols import (
    FillSource,
    IdempotencyGuard,
    MessageBusPort,
    OrderStore,
    RiskCheckResult,
    RiskManager,
)
from application.reconciliation.engine import DriftItem, ReconciliationEngine
from application.risk.context import RiskContext
from domain.commands import PlaceOrderCommand
from domain.entities import Order, Position
from domain.enums import DriftSeverity, OrderStatus, RiskLevel
from domain.events import OrderFilled, OrderPlaced, ReconciliationCompleted, ReconciliationDrift, RiskBreached, Shutdown
from domain.value_objects import (
    ComponentId,
    CorrelationId,
    InstrumentId,
    OrderId,
    Quantity,
)

_OPEN_STATUSES = frozenset({OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED})
_SEVERITY_RANK = {DriftSeverity.LOW: 0, DriftSeverity.MEDIUM: 1, DriftSeverity.HIGH: 2}


class ExecutionEngine:
    """Orchestrates place path. NEVER calls fill_source when risk denies."""

    def __init__(
        self,
        *,
        fill_source: FillSource,
        risk_manager: RiskManager,
        idempotency_guard: IdempotencyGuard,
        order_store: OrderStore | None = None,
        order_manager: Any | None = None,
        position_manager: Any | None = None,
        trading_cache: Any | None = None,
        message_bus: MessageBusPort | None = None,
        clock: Any | None = None,
        audit_sink: Any | None = None,
    ) -> None:
        self._fill = fill_source
        self._risk = risk_manager
        self._idem = idempotency_guard
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._bus = message_bus
        self._clock = clock
        self._audit_sink = audit_sink
        self._reconciler = ReconciliationEngine()
        self._order_count = 0
        if order_store is not None:
            self._store: OrderStore = order_store
        elif trading_cache is not None:
            self._store = _TradingCacheStore(trading_cache)
        else:
            self._store = InMemoryOrderStore()

    def submit(self, command: PlaceOrderCommand) -> Order | None:
        self._audit(command)
        prior = self._idem.check_and_reserve(command.correlation_id)
        if prior is not None:
            return prior  # type: ignore[return-value]

        check = self._risk.check_order(command, self._risk_context())
        self._audit(check)
        if not getattr(check, "approved", False):
            self._on_risk_deny(command, check)
            self._idem.record_result(command.correlation_id, None)
            return None

        order = self._fill.submit(command)
        self._order_count += 1
        self._apply_oms(order)
        self._idem.record_result(command.correlation_id, order)
        self._publish_success(order)
        return order

    def on_order_command(self, command: PlaceOrderCommand) -> Order | None:
        return self.submit(command)

    def cancel(self, order_id: OrderId) -> None:
        self._fill.cancel(order_id)

    def trip_kill_switch(self, reason: str = "") -> None:
        """Halt new submissions, cancel every open order, broadcast Shutdown."""
        activate = getattr(self._risk, "activate_kill_switch", None)
        if activate is not None:
            activate(reason)
        for order in self._store.all_orders():
            if order.status in _OPEN_STATUSES:
                self._fill.cancel(order.order_id)
        if self._bus is not None:
            self._bus.publish(
                Shutdown(
                    timestamp=self._now(),
                    source=ComponentId(value="execution-engine"),
                    reason=reason or "kill switch",
                )
            )

    def reconcile(
        self,
        *,
        broker_orders: list[Order] | None = None,
        broker_positions: list[Position] | None = None,
    ) -> list[DriftItem]:
        """Compare local cache vs broker snapshot; publish drift/completed events.

        No auto-trigger on broker reconnect yet — call this from an operator, CLI
        command, or future connection-lifecycle hook once one exists.
        """
        started = time.perf_counter()
        drifts: list[DriftItem] = []
        if broker_orders is not None:
            drifts += self._reconciler.compare_orders(self._store.all_orders(), broker_orders)
        if broker_positions is not None:
            local_positions = list(self._get_positions().values())
            drifts += self._reconciler.compare_positions(local_positions, broker_positions)

        if self._bus is not None:
            if drifts:
                severity = max((d.severity for d in drifts), key=lambda s: _SEVERITY_RANK[s])
                self._bus.publish(
                    ReconciliationDrift(
                        timestamp=self._now(),
                        source=ComponentId(value="execution-engine"),
                        drift_items=[f"{d.kind}:{d.key}:{d.reason}" for d in drifts],
                        severity=severity,
                    )
                )
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._bus.publish(
                ReconciliationCompleted(
                    timestamp=self._now(),
                    source=ComponentId(value="execution-engine"),
                    items_healed=0,
                    duration_ms=duration_ms,
                )
            )
        return drifts

    def _audit(self, event: Any) -> None:
        if self._audit_sink is not None:
            self._audit_sink.record(event)

    def _risk_context(self) -> RiskContext:
        """Build RiskContext from real TradingCache state (positions, PnL, order count)."""
        positions = self._get_positions()
        daily_pnl = self._compute_daily_pnl(positions)
        available_margin = self._compute_available_margin()
        return RiskContext(
            positions=positions,
            daily_pnl=daily_pnl,
            order_count=self._order_count,
            available_margin=available_margin,
        )

    def _get_positions(self) -> dict[InstrumentId, Position]:
        """Pull live positions from the TradingCache (via order_manager or store)."""
        cache = None
        if self._order_manager is not None:
            cache = getattr(self._order_manager, "_cache", None)
        elif isinstance(self._store, _TradingCacheStore):
            cache = self._store._cache

        if cache is None:
            return {}

        snap = cache.snapshot()
        raw = snap.get("positions", {})
        return {pos.instrument_id: pos for pos in raw.values()}

    def _compute_daily_pnl(self, positions: dict[InstrumentId, Position]) -> Decimal:
        """Sum realized PnL across all positions as the daily PnL proxy."""
        total = Decimal("0")
        for pos in positions.values():
            total += pos.realized_pnl.amount
        return total

    def _compute_available_margin(self) -> Decimal:
        """No margin source in TradingCache; return 0 (no-op for margin rules)."""
        return Decimal("0")

    def _now(self) -> datetime:
        if self._clock is not None:
            ts = self._clock.now()  # domain Timestamp: nanoseconds since epoch
            return datetime.fromtimestamp(ts.value / 1_000_000_000, tz=UTC)
        return datetime.now(UTC)

    def _on_risk_deny(self, command: PlaceOrderCommand, check: RiskCheckResult | Any) -> None:
        reason = getattr(check, "reason", None) or "risk denied"
        breach = RiskBreached(
            timestamp=self._now(),
            correlation_id=command.correlation_id.value,
            source=ComponentId(value="execution-engine"),
            level=RiskLevel.CRITICAL,
            reason=reason,
            instrument_id=command.instrument_id,
        )
        self._audit(breach)
        if self._bus is not None:
            self._bus.publish(breach)

    def _apply_oms(self, order: Order) -> None:
        self._store.upsert(order)
        if self._order_manager is not None:
            self._order_manager.upsert(order)
        if self._position_manager is not None and order.status is OrderStatus.FILLED:
            self._position_manager.apply(order)

    def _publish_success(self, order: Order) -> None:
        ts = self._now()
        corr = order.correlation_id.value if isinstance(order.correlation_id, CorrelationId) else None
        placed = OrderPlaced(
            timestamp=ts,
            correlation_id=corr,
            source=ComponentId(value="execution-engine"),
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            side=order.side,
            quantity=order.quantity,
        )
        self._audit(placed)
        if self._bus is not None:
            self._bus.publish(placed)

        if order.status is OrderStatus.FILLED:
            filled = order.filled_quantity if order.filled_quantity.value else order.quantity
            avg = order.price
            if avg is None:
                return
            fill_event = OrderFilled(
                timestamp=ts,
                correlation_id=corr,
                source=ComponentId(value="execution-engine"),
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                filled_qty=filled if isinstance(filled, Quantity) else order.quantity,
                avg_price=avg,
            )
            self._audit(fill_event)
            if self._bus is not None:
                self._bus.publish(fill_event)


class _TradingCacheStore:
    """Adapt TradingCache to OrderStore without depending on OMS layout."""

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._by_corr: dict[str, Order] = {}

    def upsert(self, order: Order) -> None:
        self._cache.set_order(order)
        self._by_corr[str(order.correlation_id.value)] = order

    def get(self, order_id: OrderId) -> Order | None:
        return self._cache.get_order(order_id)

    def get_by_correlation(self, correlation_id: CorrelationId) -> Order | None:
        return self._by_corr.get(str(correlation_id.value))

    def all_orders(self) -> list[Order]:
        snap = self._cache.snapshot()
        return list(snap.get("orders", {}).values())
