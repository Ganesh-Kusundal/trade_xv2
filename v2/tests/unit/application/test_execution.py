"""Unit tests for ExecutionEngine and FillSource implementations.

TDD: these tests define the contract. The implementation must satisfy them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import uuid4


from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_sources import (
    BrokerFillSource,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
)
from application.execution.order_store import InMemoryOrderStore
from application.execution.protocols import RiskCheckResult
from application.risk.risk_manager import RiskManager
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.events import (
    OrderFilled,
    OrderPlaced,
    ReconciliationCompleted,
    ReconciliationDrift,
    RiskBreached,
    Shutdown,
)
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity
from infrastructure.clock import FakeClock
from infrastructure.observability.audit import AuditSink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_command(cid: CorrelationId | None = None, qty: str = "10") -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid or CorrelationId(value=uuid4()),
    )


class _ApproveRisk:
    def check_order(self, command: PlaceOrderCommand, context: object | None = None) -> RiskCheckResult:
        return RiskCheckResult(approved=True)


class _DenyRisk:
    def check_order(self, command: PlaceOrderCommand, context: object | None = None) -> RiskCheckResult:
        return RiskCheckResult(approved=False, reason="max exposure exceeded")


class _RecordingIdempotency:
    def __init__(self) -> None:
        self._results: dict[object, object] = {}

    def check_and_reserve(self, correlation_id: CorrelationId) -> object | None:
        key = correlation_id.value
        return self._results.get(key)

    def record_result(self, correlation_id: CorrelationId, result: object) -> None:
        self._results[correlation_id.value] = result


class _RecordingFillSource:
    def __init__(self) -> None:
        self.submissions: list[PlaceOrderCommand] = []

    def submit(self, command: PlaceOrderCommand) -> Order:
        self.submissions.append(command)
        order = Order(
            order_id=OrderId(value=f"fill-{len(self.submissions)}"),
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


class _FakeBrokerAdapter:
    def submit_order(self, command: PlaceOrderCommand) -> Order:
        order = Order(
            order_id=OrderId(value="BROK-1"),
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


class _PassthroughIdempotency:
    def check_and_reserve(self, correlation_id: CorrelationId) -> None:
        return None

    def record_result(self, correlation_id: CorrelationId, result: object) -> None:
        pass


# ---------------------------------------------------------------------------
# ExecutionEngine tests
# ---------------------------------------------------------------------------

class TestExecutionEngineValidOrder:
    def test_processes_valid_order_command(self) -> None:
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        cmd = _make_command()
        order = engine.submit(cmd)
        assert order is not None
        assert order.status is OrderStatus.FILLED
        assert order.filled_quantity == cmd.quantity

    def test_order_stored_in_order_store(self) -> None:
        store = InMemoryOrderStore()
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=store,
        )
        cmd = _make_command()
        order = engine.submit(cmd)
        assert store.get(order.order_id) is not None

    def test_on_order_command_delegates_to_submit(self) -> None:
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        cmd = _make_command()
        order = engine.on_order_command(cmd)
        assert order is not None
        assert order.status is OrderStatus.FILLED


class TestExecutionEngineIdempotency:
    def test_duplicate_correlation_id_returns_prior_result(self) -> None:
        fill = _RecordingFillSource()
        idem = _RecordingIdempotency()
        engine = ExecutionEngine(
            fill_source=fill,
            risk_manager=_ApproveRisk(),
            idempotency_guard=idem,
            order_store=InMemoryOrderStore(),
        )
        cmd = _make_command()
        first = engine.submit(cmd)
        second = engine.submit(cmd)
        assert fill.submissions.__len__() == 1
        assert second is first

    def test_different_correlation_ids_are_independent(self) -> None:
        fill = _RecordingFillSource()
        engine = ExecutionEngine(
            fill_source=fill,
            risk_manager=_ApproveRisk(),
            idempotency_guard=_RecordingIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        cmd1 = _make_command(CorrelationId(value=uuid4()))
        cmd2 = _make_command(CorrelationId(value=uuid4()))
        engine.submit(cmd1)
        engine.submit(cmd2)
        assert fill.submissions.__len__() == 2


class TestExecutionEngineRiskDenial:
    def test_risk_denied_returns_none(self) -> None:
        fill = _RecordingFillSource()
        engine = ExecutionEngine(
            fill_source=fill,
            risk_manager=_DenyRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        result = engine.submit(_make_command())
        assert result is None

    def test_risk_denied_skips_fill_source(self) -> None:
        fill = _RecordingFillSource()
        engine = ExecutionEngine(
            fill_source=fill,
            risk_manager=_DenyRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        engine.submit(_make_command())
        assert fill.submissions == []


class TestExecutionEngineFillProcessing:
    def test_fill_transitions_order_to_filled(self) -> None:
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        order = engine.submit(_make_command())
        assert order.status is OrderStatus.FILLED

    def test_fill_records_filled_quantity(self) -> None:
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
        )
        cmd = _make_command(qty="25")
        order = engine.submit(cmd)
        assert order.filled_quantity == Quantity(value=Decimal("25"))


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    def publish(self, message: object) -> None:
        self.published.append(message)


class TestExecutionEngineClock:
    def test_published_event_timestamp_is_datetime_with_real_clock(self) -> None:
        """Regression: Clock.now() returns a nanosecond Timestamp, not a datetime.
        _now() must convert it before stamping events (was passed through raw)."""
        bus = _RecordingBus()
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
            message_bus=bus,
            clock=FakeClock(),
        )
        engine.submit(_make_command())
        assert bus.published, "expected at least one published event"
        for event in bus.published:
            assert isinstance(event.timestamp, datetime)


class TestExecutionEngineAuditSink:
    def test_successful_order_audits_command_placed_and_fill(self) -> None:
        sink = AuditSink()
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
            audit_sink=sink,
        )
        cmd = _make_command()
        engine.submit(cmd)
        kinds = [type(r) for r in sink.records]
        assert PlaceOrderCommand in kinds
        assert OrderPlaced in kinds
        assert OrderFilled in kinds

    def test_risk_denial_audits_command_and_breach(self) -> None:
        sink = AuditSink()
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_DenyRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
            audit_sink=sink,
        )
        engine.submit(_make_command())
        # command received, risk-check result, risk-breach event
        assert len(sink.records) == 3
        assert isinstance(sink.records[0], PlaceOrderCommand)
        assert isinstance(sink.records[-1], RiskBreached)


class _OpenOrderFillSource:
    """Returns a SUBMITTED (non-terminal) order — never auto-fills."""

    def submit(self, command: PlaceOrderCommand) -> Order:
        order = Order(
            order_id=OrderId(value="open-1"),
            instrument_id=command.instrument_id,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            price=command.price,
            time_in_force=command.time_in_force,
            status=OrderStatus.PENDING,
            correlation_id=command.correlation_id,
        )
        return order.transition_to(OrderStatus.SUBMITTED)

    def __init__(self) -> None:
        self.cancelled: list[OrderId] = []

    def cancel(self, order_id: OrderId) -> None:
        self.cancelled.append(order_id)


class TestExecutionEngineKillSwitch:
    def test_trip_kill_switch_cancels_open_orders_and_publishes_shutdown(self) -> None:
        fill = _OpenOrderFillSource()
        bus = _RecordingBus()
        risk = RiskManager()
        engine = ExecutionEngine(
            fill_source=fill,
            risk_manager=risk,
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
            message_bus=bus,
        )
        engine.submit(_make_command())

        engine.trip_kill_switch("daily loss breached")

        assert fill.cancelled == [OrderId(value="open-1")]
        assert risk.is_kill_switch_active
        assert any(isinstance(m, Shutdown) for m in bus.published)

        # kill switch now blocks further submissions via RiskManager itself
        result = engine.submit(_make_command())
        assert result is None


class TestExecutionEngineReconcile:
    def test_drift_publishes_drift_then_completed(self) -> None:
        bus = _RecordingBus()
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
            message_bus=bus,
        )
        local_order = engine.submit(_make_command())
        broker_order = replace(local_order, filled_quantity=Quantity(value=Decimal("999")))

        drifts = engine.reconcile(broker_orders=[broker_order])

        assert drifts, "expected quantity mismatch drift"
        assert isinstance(bus.published[-2], ReconciliationDrift)
        assert isinstance(bus.published[-1], ReconciliationCompleted)

    def test_no_drift_publishes_completed_only(self) -> None:
        bus = _RecordingBus()
        engine = ExecutionEngine(
            fill_source=_RecordingFillSource(),
            risk_manager=_ApproveRisk(),
            idempotency_guard=_PassthroughIdempotency(),
            order_store=InMemoryOrderStore(),
            message_bus=bus,
        )
        drifts = engine.reconcile(broker_orders=[])
        assert drifts == []
        assert isinstance(bus.published[-1], ReconciliationCompleted)
        assert not any(isinstance(m, ReconciliationDrift) for m in bus.published)


# ---------------------------------------------------------------------------
# SimulatedFillSource tests
# ---------------------------------------------------------------------------

class TestSimulatedFillSource:
    def test_returns_immediate_fill(self) -> None:
        src = SimulatedFillSource()
        cmd = _make_command()
        order = src.submit(cmd)
        assert order.status is OrderStatus.FILLED

    def test_fill_at_command_price(self) -> None:
        src = SimulatedFillSource()
        cmd = _make_command()
        order = src.submit(cmd)
        assert order.price == Price(value=Decimal("2500"))

    def test_fill_quantity_matches_command(self) -> None:
        src = SimulatedFillSource()
        cmd = _make_command(qty="50")
        order = src.submit(cmd)
        assert order.filled_quantity == Quantity(value=Decimal("50"))

    def test_cancel_is_noop(self) -> None:
        src = SimulatedFillSource()
        result = src.cancel(OrderId(value="any"))
        assert result is None


# ---------------------------------------------------------------------------
# Four-mode parity
# ---------------------------------------------------------------------------

class TestFourModeParity:
    def test_all_modes_produce_filled_order(self) -> None:
        cid = CorrelationId(value=uuid4())
        cmd = _make_command(cid)

        sim_order = SimulatedFillSource().submit(cmd)

        modes: dict[str, object] = {
            "simulated": SimulatedFillSource(),
            "paper": PaperFillSource(gateway=None),
            "broker": BrokerFillSource(adapter=_FakeBrokerAdapter()),
            "replay": ReplayFillSource(recorded_fills={cid: sim_order}),
        }

        results: dict[str, Order] = {}
        for name, src in modes.items():
            engine = ExecutionEngine(
                fill_source=src,
                risk_manager=_ApproveRisk(),
                idempotency_guard=_PassthroughIdempotency(),
                order_store=InMemoryOrderStore(),
            )
            results[name] = engine.submit(cmd)

        for name, order in results.items():
            assert order is not None, f"{name}: order is None"
            assert order.status is OrderStatus.FILLED, f"{name}: status={order.status}"

    def test_all_modes_same_filled_qty(self) -> None:
        cid = CorrelationId(value=uuid4())
        cmd = _make_command(cid)

        sim_order = SimulatedFillSource().submit(cmd)

        modes: dict[str, object] = {
            "simulated": SimulatedFillSource(),
            "paper": PaperFillSource(gateway=None),
            "broker": BrokerFillSource(adapter=_FakeBrokerAdapter()),
            "replay": ReplayFillSource(recorded_fills={cid: sim_order}),
        }

        qtys: dict[str, Quantity] = {}
        for name, src in modes.items():
            engine = ExecutionEngine(
                fill_source=src,
                risk_manager=_ApproveRisk(),
                idempotency_guard=_PassthroughIdempotency(),
                order_store=InMemoryOrderStore(),
            )
            order = engine.submit(cmd)
            qtys[name] = order.filled_quantity

        unique_qtys = {q.value for q in qtys.values()}
        assert len(unique_qtys) == 1, f"qty mismatch: {qtys}"
        assert next(iter(unique_qtys)) == Decimal("10")
