"""Four-mode parity: Simulated / Paper / Broker(Fake) / Replay → same FILLED qty."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from application.execution import (
    BrokerFillSource,
    ExecutionEngine,
    InMemoryOrderStore,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
)
from application.execution.protocols import RiskCheckResult
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


pytestmark = pytest.mark.parity


def _cmd(cid: CorrelationId) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId(value="NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("5")),
        price=Price(value=Decimal("100")),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid,
    )


class ApproveRisk:
    def check_order(self, command: PlaceOrderCommand, context: object | None = None) -> RiskCheckResult:
        return RiskCheckResult(approved=True)


class PassthroughIdempotency:
    """Fresh reservation every call — parity compares fill sources, not idempotency."""

    def check_and_reserve(self, correlation_id):
        return None

    def record_result(self, correlation_id, result) -> None:
        return None


class FakeBrokerAdapter:
    def submit_order(self, command: PlaceOrderCommand) -> Order:
        order = Order(
            order_id=OrderId(value=f"brk-{command.correlation_id.value.hex[:8]}"),
            instrument_id=command.instrument_id,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            time_in_force=command.time_in_force,
            status=OrderStatus.PENDING,
            correlation_id=command.correlation_id,
        )
        order.transition_to(OrderStatus.SUBMITTED)
        order.transition_to(OrderStatus.FILLED)
        order.filled_quantity = command.quantity
        return order

    def cancel_order(self, order_id: OrderId) -> None:
        return None


def _run(fill_source) -> Order:
    engine = ExecutionEngine(
        fill_source=fill_source,
        risk_manager=ApproveRisk(),
        idempotency_guard=PassthroughIdempotency(),
        order_store=InMemoryOrderStore(),
    )
    order = engine.submit(_cmd(CorrelationId(value=uuid4())))
    assert order is not None
    return order


def test_four_mode_parity_filled_qty() -> None:
    cid = CorrelationId(value=uuid4())
    cmd = _cmd(cid)
    sim_order = SimulatedFillSource().submit(cmd)
    recorded = {cid: sim_order}

    modes = {
        "simulated": SimulatedFillSource(),
        "paper": PaperFillSource(gateway=None),  # falls back to simulate
        "broker": BrokerFillSource(adapter=FakeBrokerAdapter()),
        "replay": ReplayFillSource(recorded_fills=recorded),
    }

    results: dict[str, Order] = {}
    for name, src in modes.items():
        if name == "replay":
            # replay keyed by same correlation_id
            engine = ExecutionEngine(
                fill_source=src,
                risk_manager=ApproveRisk(),
                idempotency_guard=PassthroughIdempotency(),
                order_store=InMemoryOrderStore(),
            )
            results[name] = engine.submit(cmd)  # type: ignore[assignment]
        else:
            results[name] = _run(src)

    statuses = {name: o.status for name, o in results.items()}
    qtys = {name: o.filled_quantity for name, o in results.items()}
    assert all(s is OrderStatus.FILLED for s in statuses.values()), statuses
    assert len({q.value for q in qtys.values()}) == 1, qtys
    assert next(iter(qtys.values())) == Quantity(value=Decimal("5"))
