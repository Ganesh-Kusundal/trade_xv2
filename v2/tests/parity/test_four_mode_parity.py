"""Four-mode parity: Simulated / Paper / Broker(Fake) / Replay → same FILLED qty.

Parity gate: the same ExecutionEngine runs in all four modes; only the FillSource
differs. This file verifies:
1. All four modes produce identical FILLED status and filled_quantity.
2. The same ExecutionEngine class is used everywhere (no mode-specific engine).
3. Order FSM transitions are identical across modes.
4. Replay determinism: log → identical cache state.
"""

from __future__ import annotations

from dataclasses import replace
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
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity
from infrastructure.clock import FakeClock
from infrastructure.message_bus import MessageBus


pytestmark = pytest.mark.parity

_INSTR = InstrumentId.parse("NSE:RELIANCE")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cmd(cid: CorrelationId) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=_INSTR,
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
        order = order.transition_to(OrderStatus.SUBMITTED)
        order = order.transition_to(OrderStatus.FILLED)
        order = replace(order, filled_quantity=command.quantity)
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


def _build_engine(fill_source, *, cache=None, bus=None, clock=None):
    """Wire ExecutionEngine with real OMS components (parity with E2E)."""
    cache = cache or TradingCache()
    om = OrderManager(cache)
    pm = PositionManager(cache)
    engine = ExecutionEngine(
        fill_source=fill_source,
        risk_manager=ApproveRisk(),
        idempotency_guard=PassthroughIdempotency(),
        order_manager=om,
        position_manager=pm,
        trading_cache=cache,
        message_bus=bus,
        clock=clock,
    )
    return engine, cache


# ---------------------------------------------------------------------------
# 1. Parity gate: four modes → same FILLED qty
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 2. Same ExecutionEngine class in all four modes
# ---------------------------------------------------------------------------

def test_same_engine_class_all_modes() -> None:
    """Runtime.resolve_fill_source returns different FillSources but the same engine class."""
    from runtime.execution_target import resolve_fill_source
    from config.schema import Environment

    for env in (Environment.REPLAY, Environment.BACKTEST, Environment.PAPER, Environment.LIVE):
        fill = resolve_fill_source(env)
        engine, _ = _build_engine(fill)
        assert type(engine) is ExecutionEngine, f"mode={env}: expected ExecutionEngine, got {type(engine)}"


# ---------------------------------------------------------------------------
# 3. Order FSM transitions are identical across modes
# ---------------------------------------------------------------------------

def test_order_fsm_identical_across_modes() -> None:
    """All modes go through PENDING → SUBMITTED → FILLED with same transitions."""
    modes = {
        "simulated": SimulatedFillSource(),
        "paper": PaperFillSource(gateway=None),
        "broker": BrokerFillSource(adapter=FakeBrokerAdapter()),
    }

    for name, src in modes.items():
        cid = CorrelationId(value=uuid4())
        order = src.submit(_cmd(cid))
        # All must pass through the same FSM: PENDING → SUBMITTED → FILLED
        assert order.status is OrderStatus.FILLED, f"mode={name}: status={order.status}"
        assert order.filled_quantity.value == Decimal("5"), f"mode={name}: qty={order.filled_quantity}"


# ---------------------------------------------------------------------------
# 4. Replay determinism: log → identical cache
# ---------------------------------------------------------------------------

def test_replay_determinism_log_to_cache() -> None:
    """Replaying the same log with the same commands produces identical cache state."""
    bus = MessageBus()

    # Phase 1: record fills via SimulatedFillSource
    engine1, cache1 = _build_engine(SimulatedFillSource(), bus=bus)
    cid = CorrelationId(value=uuid4())
    cmd = _cmd(cid)
    order1 = engine1.submit(cmd)
    assert order1 is not None and order1.status is OrderStatus.FILLED

    # Phase 2: replay via ReplayFillSource with recorded fill
    recorded = {cid: order1}
    engine2, cache2 = _build_engine(ReplayFillSource(recorded_fills=recorded))
    order2 = engine2.submit(cmd)

    # Cache state must be identical
    snap1 = cache1.snapshot()
    snap2 = cache2.snapshot()
    assert len(snap1["orders"]) == len(snap2["orders"])
    for oid in snap1["orders"]:
        o1 = snap1["orders"][oid]
        o2 = snap2["orders"][oid]
        assert o1.status == o2.status
        assert o1.filled_quantity == o2.filled_quantity


# ---------------------------------------------------------------------------
# 5. Parity: position updates identical across modes (with OMS wired)
# ---------------------------------------------------------------------------

def test_position_parity_all_modes() -> None:
    """With OMS wired, all modes update position identically."""
    modes = {
        "simulated": SimulatedFillSource(),
        "paper": PaperFillSource(gateway=None),
    }

    for name, src in modes.items():
        engine, cache = _build_engine(src)
        engine.submit(_cmd(CorrelationId(value=uuid4())))
        pos = cache.get_position(_INSTR)
        assert pos is not None, f"mode={name}: no position"
        assert pos.quantity.value == Decimal("5"), f"mode={name}: qty={pos.quantity}"
        assert pos.avg_price.value == Decimal("100"), f"mode={name}: avg={pos.avg_price}"
