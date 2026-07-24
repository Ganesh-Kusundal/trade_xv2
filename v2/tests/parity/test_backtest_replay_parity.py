"""Determinism test harness: Backtest vs Replay parity.

This test verifies deterministic execution across:
1. Backtest determinism: Running backtest twice with identical inputs = identical outputs
2. ReplayEngine determinism: Replaying message log produces identical message sequence
3. Fill source parity: SimulatedFillSource vs ReplayFillSource produce identical cache state
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from application.analytics.engines import BacktestEngine, ReplayEngine
from application.execution import (
    ExecutionEngine,
    InMemoryOrderStore,
    ReplayFillSource,
    SimulatedFillSource,
)
from application.execution.protocols import RiskCheckResult
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from application.strategy.buy_and_hold import BuyAndHold
from domain.commands import PlaceOrderCommand
from domain.entities import Bar, Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Price, Quantity, TimeFrame
from infrastructure.clock import FakeClock
from infrastructure.message_bus import InMemoryMessageLog, MessageBus


pytestmark = pytest.mark.parity


_INSTR = InstrumentId.parse("NSE:RELIANCE")


def _bars(n: int = 5) -> list[Bar]:
    """Generate N daily bars with incrementing prices."""
    out: list[Bar] = []
    start = datetime(2024, 1, 2, tzinfo=UTC)
    for i in range(n):
        px = Price(value=Decimal(str(100 + i)))
        out.append(
            Bar(
                instrument_id=_INSTR,
                open=px,
                high=px,
                low=px,
                close=px,
                volume=Quantity(value=Decimal("1")),
                timeframe=TimeFrame(value="1d"),
                timestamp=start + timedelta(days=i),
            )
        )
    return out


class _ApproveRisk:
    def check_order(self, command: object, context: object | None = None) -> RiskCheckResult:
        return RiskCheckResult(approved=True)


class _MemoryIdempotency:
    """Matches ExecutionEngine: None = new; non-None = prior result."""

    def __init__(self) -> None:
        self._results: dict[object, object] = {}

    def check_and_reserve(self, correlation_id: object) -> object | None:
        key = getattr(correlation_id, "value", correlation_id)
        return self._results.get(key)

    def record_result(self, correlation_id: object, result: object) -> None:
        key = getattr(correlation_id, "value", correlation_id)
        self._results[key] = result


# Use fixed correlation IDs for deterministic testing
_FIXED_CID = CorrelationId(value=uuid4())


def _build_backtest_components(
    cache: TradingCache | None = None,
    correlation_id: CorrelationId | None = None,
) -> tuple[BacktestEngine, MessageBus, FakeClock, ExecutionEngine, BuyAndHold, TradingCache]:
    """Build the standard components for a backtest run."""
    bus = MessageBus()
    clock = FakeClock(start=datetime(2024, 1, 1, tzinfo=UTC))

    if cache is None:
        cache = TradingCache()
    om = OrderManager(cache)
    pm = PositionManager(cache)

    ee = ExecutionEngine(
        fill_source=SimulatedFillSource(),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om,
        position_manager=pm,
        trading_cache=cache,
        message_bus=bus,
        clock=clock,
    )

    strategy = BuyAndHold(
        bus=bus,
        quantity=Quantity(value=Decimal("2")),
        correlation_id=correlation_id or _FIXED_CID,
    )

    engine = BacktestEngine(
        bus=bus,
        clock=clock,
        execution_engine=ee,
    )
    return engine, bus, clock, ee, strategy, cache


def _snapshot_positions(cache: TradingCache) -> dict[str, tuple[Quantity, Price]]:
    """Extract positions as dict of instrument_id -> (quantity, avg_price)."""
    snap = cache.snapshot()
    return {
        str(inst_id): (pos.quantity, pos.avg_price)
        for inst_id, pos in snap["positions"].items()
    }


def _snapshot_orders_by_cid(cache: TradingCache) -> dict[str, tuple[OrderStatus, Quantity]]:
    """Extract orders keyed by correlation_id -> (status, filled_qty)."""
    snap = cache.snapshot()
    return {
        str(order.correlation_id.value): (order.status, order.filled_quantity)
        for order in snap["orders"].values()
    }


# ---------------------------------------------------------------------------
# 1. Backtest Determinism: Same inputs -> Same outputs
# ---------------------------------------------------------------------------


def test_backtest_deterministic_trade_count():
    """Running backtest twice with identical setup produces identical trade count."""
    # Run 1
    engine1, bus1, clock1, ee1, strategy1, cache1 = _build_backtest_components()
    message_log1 = InMemoryMessageLog()
    bus1._message_log = message_log1
    bt_result1 = engine1.run(bars=_bars(5), strategy=strategy1)

    # Run 2 (fresh components, same setup)
    engine2, bus2, clock2, ee2, strategy2, cache2 = _build_backtest_components()
    message_log2 = InMemoryMessageLog()
    bus2._message_log = message_log2
    bt_result2 = engine2.run(bars=_bars(5), strategy=strategy2)

    # Parity assertions
    assert bt_result2.trade_count == bt_result1.trade_count
    assert bt_result2.metrics["bars_processed"] == bt_result1.metrics["bars_processed"]
    assert bt_result2.metrics["trades"] == bt_result1.metrics["trades"]


def test_backtest_deterministic_cache_state():
    """Running backtest twice produces identical TradingCache state."""
    # Run 1
    cache1 = TradingCache()
    engine1, bus1, clock1, ee1, strategy1, _ = _build_backtest_components(cache=cache1)
    message_log1 = InMemoryMessageLog()
    bus1._message_log = message_log1
    engine1.run(bars=_bars(5), strategy=strategy1)

    # Run 2
    cache2 = TradingCache()
    engine2, bus2, clock2, ee2, strategy2, _ = _build_backtest_components(cache=cache2)
    message_log2 = InMemoryMessageLog()
    bus2._message_log = message_log2
    engine2.run(bars=_bars(5), strategy=strategy2)

    # Compare cache snapshots by correlation_id (order_id is random)
    pos1 = _snapshot_positions(cache1)
    pos2 = _snapshot_positions(cache2)
    assert pos1 == pos2, f"Positions differ: {pos1} != {pos2}"

    orders1 = _snapshot_orders_by_cid(cache1)
    orders2 = _snapshot_orders_by_cid(cache2)
    assert orders1 == orders2, f"Orders differ: {orders1} != {orders2}"


def test_backtest_deterministic_order_fsm():
    """Backtest produces identical order FSM transitions on repeated runs."""
    cache1 = TradingCache()
    engine1, bus1, clock1, ee1, strategy1, _ = _build_backtest_components(cache=cache1)
    message_log1 = InMemoryMessageLog()
    bus1._message_log = message_log1
    engine1.run(bars=_bars(3), strategy=strategy1)

    cache2 = TradingCache()
    engine2, bus2, clock2, ee2, strategy2, _ = _build_backtest_components(cache=cache2)
    message_log2 = InMemoryMessageLog()
    bus2._message_log = message_log2
    engine2.run(bars=_bars(3), strategy=strategy2)

    orders1 = _snapshot_orders_by_cid(cache1)
    orders2 = _snapshot_orders_by_cid(cache2)

    for cid in orders1:
        status1, filled1 = orders1[cid]
        status2, filled2 = orders2[cid]
        # All orders should go PENDING -> SUBMITTED -> FILLED
        assert status1 is OrderStatus.FILLED, f"Order {cid} not FILLED in run 1"
        assert status2 is OrderStatus.FILLED, f"Order {cid} not FILLED in run 2"
        assert filled1 == filled2, f"Filled qty differs for {cid}: {filled1} != {filled2}"


# ---------------------------------------------------------------------------
# 2. ReplayEngine Determinism: Message log replay produces identical sequence
# ---------------------------------------------------------------------------


def test_replay_engine_deterministic_message_order():
    """ReplayEngine publishes messages in exact same order as recorded."""
    log = InMemoryMessageLog()
    record_bus = MessageBus(message_log=log)

    # Publish a sequence of messages with timestamps
    timestamps = [datetime(2024, 1, 1, i, tzinfo=UTC) for i in range(10)]
    for i, ts in enumerate(timestamps):
        record_bus.publish(_TestMessage(seq=i, timestamp=ts))

    # Replay
    replay_bus = MessageBus()
    seen: list[_TestMessage] = []
    replay_bus.subscribe(_TestMessage, seen.append)

    replay_engine = ReplayEngine(bus=replay_bus, message_log=log)
    count = replay_engine.run()

    assert count == 10
    assert len(seen) == 10
    assert [m.seq for m in seen] == list(range(10)), "Message order not preserved"
    assert [m.timestamp for m in seen] == timestamps, "Timestamps not preserved"


def test_replay_engine_time_window_filtering():
    """ReplayEngine respects start/end time filters."""
    log = InMemoryMessageLog()
    record_bus = MessageBus(message_log=log)

    early = _TestMessage(seq=0, timestamp=datetime(2024, 1, 1, tzinfo=UTC))
    mid = _TestMessage(seq=1, timestamp=datetime(2024, 6, 1, tzinfo=UTC))
    late = _TestMessage(seq=2, timestamp=datetime(2024, 12, 1, tzinfo=UTC))
    for msg in (early, mid, late):
        record_bus.publish(msg)

    # Replay only mid
    replay_bus = MessageBus()
    seen: list[_TestMessage] = []
    replay_bus.subscribe(_TestMessage, seen.append)

    replay_engine = ReplayEngine(bus=replay_bus, message_log=log)
    count = replay_engine.run(
        start=datetime(2024, 3, 1, tzinfo=UTC),
        end=datetime(2024, 9, 1, tzinfo=UTC),
    )

    assert count == 1
    assert len(seen) == 1
    assert seen[0].seq == 1


# ---------------------------------------------------------------------------
# 3. Fill Source Parity: SimulatedFillSource vs ReplayFillSource
# ---------------------------------------------------------------------------


def test_fill_source_parity_simulated_vs_replay():
    """ReplayFillSource with recorded fills produces identical cache as SimulatedFillSource."""
    # Phase 1: Run with SimulatedFillSource
    cache1 = TradingCache()
    om1 = OrderManager(cache1)
    pm1 = PositionManager(cache1)

    ee1 = ExecutionEngine(
        fill_source=SimulatedFillSource(),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om1,
        position_manager=pm1,
        trading_cache=cache1,
    )

    cid = CorrelationId(value=uuid4())
    cmd = PlaceOrderCommand(
        instrument_id=_INSTR,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("5")),
        price=Price(value=Decimal("100")),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid,
    )
    order1 = ee1.submit(cmd)
    assert order1 is not None and order1.status is OrderStatus.FILLED

    # Capture the fill
    recorded_fills = {cid: order1}

    # Phase 2: Run with ReplayFillSource
    cache2 = TradingCache()
    om2 = OrderManager(cache2)
    pm2 = PositionManager(cache2)

    ee2 = ExecutionEngine(
        fill_source=ReplayFillSource(recorded_fills=recorded_fills),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om2,
        position_manager=pm2,
        trading_cache=cache2,
    )

    order2 = ee2.submit(cmd)
    assert order2 is not None and order2.status is OrderStatus.FILLED

    # Compare cache states by correlation_id
    pos1 = _snapshot_positions(cache1)
    pos2 = _snapshot_positions(cache2)
    assert pos1 == pos2, f"Positions differ: {pos1} != {pos2}"

    orders1 = _snapshot_orders_by_cid(cache1)
    orders2 = _snapshot_orders_by_cid(cache2)
    assert orders1 == orders2, f"Orders differ: {orders1} != {orders2}"


def test_replay_fill_source_deterministic():
    """ReplayFillSource produces identical results on repeated use with same recorded fills."""
    cache1 = TradingCache()
    om1 = OrderManager(cache1)
    pm1 = PositionManager(cache1)

    ee1 = ExecutionEngine(
        fill_source=SimulatedFillSource(),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om1,
        position_manager=pm1,
        trading_cache=cache1,
    )

    cid = CorrelationId(value=uuid4())
    cmd = PlaceOrderCommand(
        instrument_id=_INSTR,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("5")),
        price=Price(value=Decimal("100")),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid,
    )
    order1 = ee1.submit(cmd)
    recorded_fills = {cid: order1}

    # Run replay twice with same recorded fills
    cache2a = TradingCache()
    om2a = OrderManager(cache2a)
    pm2a = PositionManager(cache2a)
    ee2a = ExecutionEngine(
        fill_source=ReplayFillSource(recorded_fills=recorded_fills),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om2a,
        position_manager=pm2a,
        trading_cache=cache2a,
    )
    order2a = ee2a.submit(cmd)

    cache2b = TradingCache()
    om2b = OrderManager(cache2b)
    pm2b = PositionManager(cache2b)
    ee2b = ExecutionEngine(
        fill_source=ReplayFillSource(recorded_fills=recorded_fills),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om2b,
        position_manager=pm2b,
        trading_cache=cache2b,
    )
    order2b = ee2b.submit(cmd)

    # Both replay runs should produce identical results
    assert order2a.status == order2b.status
    assert order2a.filled_quantity == order2b.filled_quantity

    pos2a = _snapshot_positions(cache2a)
    pos2b = _snapshot_positions(cache2b)
    assert pos2a == pos2b, f"Replay positions differ: {pos2a} != {pos2b}"


# ---------------------------------------------------------------------------
# 4. Integration: Backtest with ReplayFillSource parity
# ---------------------------------------------------------------------------


def test_backtest_with_replay_fill_source_parity():
    """Backtest using SimulatedFillSource vs ReplayFillSource produces identical results."""
    # Phase 1: Backtest with SimulatedFillSource (record fills)
    cache1 = TradingCache()
    om1 = OrderManager(cache1)
    pm1 = PositionManager(cache1)

    bus1 = MessageBus()
    clock1 = FakeClock(start=datetime(2024, 1, 1, tzinfo=UTC))

    ee1 = ExecutionEngine(
        fill_source=SimulatedFillSource(),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om1,
        position_manager=pm1,
        trading_cache=cache1,
        message_bus=bus1,
        clock=clock1,
    )

    strategy1 = BuyAndHold(
        bus=bus1,
        quantity=Quantity(value=Decimal("2")),
        correlation_id=_FIXED_CID,
    )

    engine1 = BacktestEngine(
        bus=bus1,
        clock=clock1,
        execution_engine=ee1,
    )

    bars = _bars(5)
    bt_result1 = engine1.run(bars=bars, strategy=strategy1)

    # Capture fills from backtest - extract by correlation_id
    recorded_fills: dict[CorrelationId, Order] = {}
    snap1 = cache1.snapshot()
    for order in snap1["orders"].values():
        if order.status is OrderStatus.FILLED:
            recorded_fills[order.correlation_id] = order

    assert len(recorded_fills) == bt_result1.trade_count

    # Phase 2: Backtest with ReplayFillSource using recorded fills
    cache2 = TradingCache()
    om2 = OrderManager(cache2)
    pm2 = PositionManager(cache2)

    bus2 = MessageBus()
    clock2 = FakeClock(start=datetime(2024, 1, 1, tzinfo=UTC))

    ee2 = ExecutionEngine(
        fill_source=ReplayFillSource(recorded_fills=recorded_fills),
        risk_manager=_ApproveRisk(),
        idempotency_guard=_MemoryIdempotency(),
        order_manager=om2,
        position_manager=pm2,
        trading_cache=cache2,
        message_bus=bus2,
        clock=clock2,
    )

    strategy2 = BuyAndHold(
        bus=bus2,
        quantity=Quantity(value=Decimal("2")),
        correlation_id=_FIXED_CID,
    )

    engine2 = BacktestEngine(
        bus=bus2,
        clock=clock2,
        execution_engine=ee2,
    )

    bt_result2 = engine2.run(bars=bars, strategy=strategy2)

    # Parity assertions
    assert bt_result2.trade_count == bt_result1.trade_count
    assert bt_result2.metrics["bars_processed"] == bt_result1.metrics["bars_processed"]
    assert bt_result2.metrics["trades"] == bt_result1.metrics["trades"]

    # Cache state parity (by correlation_id)
    pos1 = _snapshot_positions(cache1)
    pos2 = _snapshot_positions(cache2)
    assert pos1 == pos2, f"Positions differ: {pos1} != {pos2}"

    orders1 = _snapshot_orders_by_cid(cache1)
    orders2 = _snapshot_orders_by_cid(cache2)
    assert orders1 == orders2, f"Orders differ: {orders1} != {orders2}"


@dataclass(frozen=True)
class _TestMessage:
    seq: int
    timestamp: datetime