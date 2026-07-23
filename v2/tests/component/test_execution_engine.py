"""ExecutionEngine: risk deny skips venue; approve fills; idempotent duplicate."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from application.execution import ExecutionEngine, InMemoryOrderStore
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


def _cmd(cid: CorrelationId | None = None, qty: str = "10") -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid or CorrelationId(value=uuid4()),
    )


class RecordingFillSource:
    def __init__(self) -> None:
        self.submissions: list[PlaceOrderCommand] = []

    def submit(self, command: PlaceOrderCommand) -> Order:
        self.submissions.append(command)
        order = Order(
            order_id=OrderId(value=f"rec-{len(self.submissions)}"),
            instrument_id=command.instrument_id,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            time_in_force=command.time_in_force,
            status=OrderStatus.PENDING,
            correlation_id=command.correlation_id,
        )
        order = order.transition_to(OrderStatus.SUBMITTED)
        order = order.transition_to(OrderStatus.FILLED)
        order = replace(order, filled_quantity=command.quantity)
        return order

    def cancel(self, order_id: OrderId) -> None:
        return None


class DenyRisk:
    def check_order(self, command: PlaceOrderCommand, context: object | None = None):
        from application.execution.protocols import RiskCheckResult

        return RiskCheckResult(approved=False, reason="oversize")


class ApproveRisk:
    def check_order(self, command: PlaceOrderCommand, context: object | None = None):
        from application.execution.protocols import RiskCheckResult

        return RiskCheckResult(approved=True)


class MemoryIdempotency:
    def __init__(self) -> None:
        self._reserved: set[object] = set()
        self._results: dict[object, object] = {}

    def check_and_reserve(self, correlation_id):
        key = correlation_id.value
        if key in self._results:
            return self._results[key]
        if key in self._reserved:
            return self._results.get(key)
        self._reserved.add(key)
        return None

    def record_result(self, correlation_id, result) -> None:
        self._results[correlation_id.value] = result


def test_risk_deny_never_calls_fill_source() -> None:
    fill = RecordingFillSource()
    engine = ExecutionEngine(
        fill_source=fill,
        risk_manager=DenyRisk(),
        idempotency_guard=MemoryIdempotency(),
        order_store=InMemoryOrderStore(),
    )
    result = engine.submit(_cmd())
    assert fill.submissions == []
    assert result is None or getattr(result, "status", None) != OrderStatus.FILLED


def test_risk_approve_calls_fill_source_and_stores_filled() -> None:
    fill = RecordingFillSource()
    store = InMemoryOrderStore()
    engine = ExecutionEngine(
        fill_source=fill,
        risk_manager=ApproveRisk(),
        idempotency_guard=MemoryIdempotency(),
        order_store=store,
    )
    cmd = _cmd()
    order = engine.submit(cmd)
    assert len(fill.submissions) == 1
    assert order is not None
    assert order.status is OrderStatus.FILLED
    assert order.filled_quantity == cmd.quantity
    assert store.get(order.order_id) is not None


def test_idempotent_duplicate_skips_second_fill() -> None:
    fill = RecordingFillSource()
    guard = MemoryIdempotency()
    engine = ExecutionEngine(
        fill_source=fill,
        risk_manager=ApproveRisk(),
        idempotency_guard=guard,
        order_store=InMemoryOrderStore(),
    )
    cmd = _cmd()
    first = engine.submit(cmd)
    second = engine.submit(cmd)
    assert len(fill.submissions) == 1
    assert second is first
    assert first is not None
    assert first.status is OrderStatus.FILLED
