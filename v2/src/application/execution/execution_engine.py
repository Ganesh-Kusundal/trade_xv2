"""ExecutionEngine — single order spine: idempotency → risk → fill → OMS."""

from __future__ import annotations

from datetime import UTC, datetime
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
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderStatus, RiskLevel
from domain.events import OrderFilled, OrderPlaced, RiskBreached
from domain.value_objects import ComponentId, CorrelationId, OrderId, Quantity


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
    ) -> None:
        self._fill = fill_source
        self._risk = risk_manager
        self._idem = idempotency_guard
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._bus = message_bus
        self._clock = clock
        if order_store is not None:
            self._store: OrderStore = order_store
        elif trading_cache is not None:
            self._store = _TradingCacheStore(trading_cache)
        else:
            self._store = InMemoryOrderStore()

    def submit(self, command: PlaceOrderCommand) -> Order | None:
        prior = self._idem.check_and_reserve(command.correlation_id)
        if prior is not None:
            return prior  # type: ignore[return-value]

        check = self._risk.check_order(command, self._risk_context())
        if not getattr(check, "approved", False):
            self._on_risk_deny(command, check)
            self._idem.record_result(command.correlation_id, None)
            return None

        order = self._fill.submit(command)
        self._apply_oms(order)
        self._idem.record_result(command.correlation_id, order)
        self._publish_success(order)
        return order

    def on_order_command(self, command: PlaceOrderCommand) -> Order | None:
        return self.submit(command)

    def cancel(self, order_id: OrderId) -> None:
        self._fill.cancel(order_id)

    def _risk_context(self) -> Any:
        """Build RiskContext for C2 RiskManager; fakes ignore it."""
        try:
            from decimal import Decimal

            from application.risk.context import RiskContext

            return RiskContext(
                positions={},
                daily_pnl=Decimal("0"),
                order_count=0,
                available_margin=Decimal("0"),
            )
        except ImportError:
            return None

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(UTC)

    def _on_risk_deny(self, command: PlaceOrderCommand, check: RiskCheckResult | Any) -> None:
        if self._bus is None:
            return
        reason = getattr(check, "reason", None) or "risk denied"
        self._bus.publish(
            RiskBreached(
                timestamp=self._now(),
                correlation_id=command.correlation_id.value,
                source=ComponentId(value="execution-engine"),
                level=RiskLevel.CRITICAL,
                reason=reason,
                instrument_id=command.instrument_id,
            )
        )

    def _apply_oms(self, order: Order) -> None:
        self._store.upsert(order)
        if self._order_manager is not None:
            cache = getattr(self._order_manager, "_cache", None)
            if cache is not None and hasattr(cache, "set_order"):
                # C1 OrderManager: fill sources return terminal FILLED — write cache directly
                cache.set_order(order)
        if self._position_manager is not None and order.status is OrderStatus.FILLED:
            apply = getattr(self._position_manager, "apply_trade", None) or getattr(
                self._position_manager, "apply_fill", None
            )
            if apply is not None:
                apply(order)

    def _publish_success(self, order: Order) -> None:
        if self._bus is None:
            return
        ts = self._now()
        corr = order.correlation_id.value if isinstance(order.correlation_id, CorrelationId) else None
        self._bus.publish(
            OrderPlaced(
                timestamp=ts,
                correlation_id=corr,
                source=ComponentId(value="execution-engine"),
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=order.quantity,
            )
        )
        if order.status is OrderStatus.FILLED:
            filled = order.filled_quantity if order.filled_quantity.value else order.quantity
            avg = order.price
            if avg is None:
                return
            self._bus.publish(
                OrderFilled(
                    timestamp=ts,
                    correlation_id=corr,
                    source=ComponentId(value="execution-engine"),
                    order_id=order.order_id,
                    instrument_id=order.instrument_id,
                    side=order.side,
                    filled_qty=filled if isinstance(filled, Quantity) else order.quantity,
                    avg_price=avg,
                )
            )


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
