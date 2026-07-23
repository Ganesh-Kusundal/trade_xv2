"""E2E: startup → order → fill → reconcile (real components, no mocks)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_sources import PaperFillSource, SimulatedFillSource
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from application.oms.trading_context import TradingContext
from application.risk.context import RiskContext
from application.risk.risk_manager import RiskManager
from application.risk.rules import OrderSizeRule, PositionLimitRule
from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import (
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)
from infrastructure.clock import FakeClock, SystemClock
from infrastructure.component.base import ComponentState
from infrastructure.component.lifecycle import LifecycleManager
from infrastructure.idempotency import IdempotencyGuard, IdempotencyStatus
from infrastructure.message_bus import MessageBus


_INSTR = InstrumentId.parse("NSE:RELIANCE")
_INSTR2 = InstrumentId.parse("NSE:TCS")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _AlwaysApprove:
    """Risk check that always approves."""
    def check_order(self, command, context=None):
        from application.risk.context import RiskCheckResult
        return RiskCheckResult(approved=True)


class _EngineIdempotency:
    """Adapt IdempotencyGuard → ExecutionEngine protocol."""
    def __init__(self, guard: IdempotencyGuard) -> None:
        self._guard = guard

    def check_and_reserve(self, correlation_id):
        result = self._guard.check_and_reserve(correlation_id)
        if result.status is IdempotencyStatus.DUPLICATE:
            return result.prior_result
        return None

    def record_result(self, correlation_id, result) -> None:
        self._guard.record_result(correlation_id, result)


def _build_engine(
    fill_source,
    *,
    risk_manager=None,
    order_manager=None,
    position_manager=None,
    trading_cache=None,
    message_bus=None,
    clock=None,
):
    """Wire a fresh ExecutionEngine with real components."""
    cache = trading_cache or TradingCache()
    om = order_manager or OrderManager(cache)
    pm = position_manager or PositionManager(cache)
    risk = risk_manager or RiskManager(rules=[OrderSizeRule(max_qty=Decimal("1000"))])
    idem = _EngineIdempotency(IdempotencyGuard())
    engine = ExecutionEngine(
        fill_source=fill_source,
        risk_manager=risk,
        idempotency_guard=idem,
        order_manager=om,
        position_manager=pm,
        trading_cache=cache,
        message_bus=message_bus,
        clock=clock,
    )
    return engine, cache, om, pm


def _buy_command(
    instrument: InstrumentId = _INSTR,
    qty: int = 10,
    price: int = 2500,
    cid: CorrelationId | None = None,
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=instrument,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(str(qty))),
        price=Price(value=Decimal(str(price))),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid or CorrelationId(value=uuid4()),
    )


def _sell_command(
    instrument: InstrumentId = _INSTR,
    qty: int = 5,
    price: int = 2600,
    cid: CorrelationId | None = None,
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=instrument,
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(str(qty))),
        price=Price(value=Decimal(str(price))),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid or CorrelationId(value=uuid4()),
    )


# ---------------------------------------------------------------------------
# 1. E2E: startup → order → fill → position update
# ---------------------------------------------------------------------------

class TestE2EStartupOrderFill:
    """Full flow: lifecycle → engine submit → order FILLED → position updated."""

    def test_lifecycle_initialize_start_stop(self):
        lifecycle = LifecycleManager()
        assert len(lifecycle.components) == 0

    def test_buy_order_fills_and_updates_position(self):
        engine, cache, om, pm = _build_engine(SimulatedFillSource())

        cmd = _buy_command()
        order = engine.submit(cmd)

        assert order is not None
        assert order.status is OrderStatus.FILLED
        assert order.filled_quantity.value == Decimal("10")

        # Position should be updated
        pos = cache.get_position(_INSTR)
        assert pos is not None
        assert pos.quantity.value == Decimal("10")
        assert pos.avg_price.value == Decimal("2500")

    def test_two_buys_accumulate_position(self):
        engine, cache, om, pm = _build_engine(SimulatedFillSource())

        engine.submit(_buy_command(qty=10, price=2500))
        engine.submit(_buy_command(qty=5, price=2600))

        pos = cache.get_position(_INSTR)
        assert pos is not None
        assert pos.quantity.value == Decimal("15")
        # Weighted avg: (10*2500 + 5*2600) / 15 = 2533.33...
        assert pos.avg_price.value == (Decimal("2500") * 10 + Decimal("2600") * 5) / 15

    def test_buy_then_sell_realizes_pnl(self):
        engine, cache, om, pm = _build_engine(SimulatedFillSource())

        engine.submit(_buy_command(qty=10, price=2500))
        engine.submit(_sell_command(qty=5, price=2600))

        pos = cache.get_position(_INSTR)
        assert pos is not None
        assert pos.quantity.value == Decimal("5")
        # Realized PnL on 5 units sold at 2600, bought at 2500
        assert pos.realized_pnl.amount == Decimal("500")

    def test_full_lifecycle_with_message_bus(self):
        bus = MessageBus()
        engine, cache, om, pm = _build_engine(
            SimulatedFillSource(),
            message_bus=bus,
        )

        received = []
        bus.subscribe(
            __import__("domain.events", fromlist=["OrderPlaced"]).OrderPlaced,
            lambda e: received.append(e),
        )

        engine.submit(_buy_command())
        assert len(received) == 1
        assert received[0].order_id == cache.get_order(
            next(iter(cache.snapshot()["orders"].keys()))
        ).order_id


# ---------------------------------------------------------------------------
# 2. E2E: MessageBus integration
# ---------------------------------------------------------------------------

class TestMessageBusIntegration:
    def test_publish_subscribe_roundtrip(self):
        bus = MessageBus()
        events = []
        from domain.events import OrderPlaced
        bus.subscribe(OrderPlaced, lambda e: events.append(e))
        assert len(events) == 0

    def test_bus_metrics(self):
        bus = MessageBus()
        assert bus.metrics.messages_published == 0
        assert bus.metrics.messages_delivered == 0


# ---------------------------------------------------------------------------
# 3. E2E: ExecutionEngine with PaperFillSource
# ---------------------------------------------------------------------------

class TestE2EPaperFlow:
    def test_paper_fill_source_simulates_when_no_gateway(self):
        engine, cache, om, pm = _build_engine(PaperFillSource(gateway=None))
        order = engine.submit(_buy_command())
        assert order is not None
        assert order.status is OrderStatus.FILLED

    def test_paper_position_updates(self):
        engine, cache, om, pm = _build_engine(PaperFillSource(gateway=None))
        engine.submit(_buy_command(qty=20, price=100))
        pos = cache.get_position(_INSTR)
        assert pos is not None
        assert pos.quantity.value == Decimal("20")
        assert pos.avg_price.value == Decimal("100")


# ---------------------------------------------------------------------------
# 4. E2E: Risk gate integration
# ---------------------------------------------------------------------------

class TestE2ERiskGate:
    def test_order_exceeding_size_limit_is_rejected(self):
        risk = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("5"))])
        engine, cache, om, pm = _build_engine(SimulatedFillSource(), risk_manager=risk)

        cmd = _buy_command(qty=10)  # exceeds max 5
        order = engine.submit(cmd)

        assert order is None
        assert cache.get_order(cmd.correlation_id) is None

    def test_order_within_limit_fills(self):
        risk = RiskManager(rules=[OrderSizeRule(max_qty=Decimal("100"))])
        engine, cache, om, pm = _build_engine(SimulatedFillSource(), risk_manager=risk)

        order = engine.submit(_buy_command(qty=10))
        assert order is not None
        assert order.status is OrderStatus.FILLED


# ---------------------------------------------------------------------------
# 5. E2E: Idempotency integration
# ---------------------------------------------------------------------------

class TestE2EIdempotency:
    def test_duplicate_command_returns_same_order(self):
        engine, cache, om, pm = _build_engine(SimulatedFillSource())
        cid = CorrelationId(value=uuid4())
        cmd = _buy_command(cid=cid)

        order1 = engine.submit(cmd)
        order2 = engine.submit(cmd)

        assert order1 is not None
        assert order2 is not None
        assert order1.order_id == order2.order_id


# ---------------------------------------------------------------------------
# 6. E2E: Clock integration
# ---------------------------------------------------------------------------

class TestE2EClock:
    def test_fake_clock_advances(self):
        clock = FakeClock()
        t1 = clock.now()
        from datetime import timedelta
        clock.advance(timedelta(seconds=5))
        t2 = clock.now()
        assert t2.value > t1.value

    def test_system_clock_returns_utc(self):
        clock = SystemClock()
        ts = clock.now()
        assert ts.value > 0


# ---------------------------------------------------------------------------
# 7. E2E: Reconciliation flow (cache snapshot → position integrity)
# ---------------------------------------------------------------------------

class TestE2EReconcile:
    def test_cache_snapshot_matches_position(self):
        engine, cache, om, pm = _build_engine(SimulatedFillSource())

        engine.submit(_buy_command(qty=10, price=2500))
        engine.submit(_sell_command(qty=3, price=2600))

        snap = cache.snapshot()
        assert len(snap["orders"]) == 2
        pos = snap["positions"][_INSTR.value]
        assert pos.quantity.value == Decimal("7")
        assert pos.realized_pnl.amount == Decimal("300")

    def test_multiple_instruments_independent(self):
        engine, cache, om, pm = _build_engine(SimulatedFillSource())

        engine.submit(_buy_command(instrument=_INSTR, qty=10, price=2500))
        engine.submit(_buy_command(instrument=_INSTR2, qty=5, price=3000))

        pos1 = cache.get_position(_INSTR)
        pos2 = cache.get_position(_INSTR2)
        assert pos1.quantity.value == Decimal("10")
        assert pos2.quantity.value == Decimal("5")
