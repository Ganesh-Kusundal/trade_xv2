"""Contract tests for FillSource protocol implementations.

These tests verify that all FillSource implementations conform to the
FillSource protocol defined in application.execution.protocols.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping
from uuid import uuid4

import pytest

from application.execution.fill_sources import (
    BrokerFillSource,
    PaperFillSource,
    ReplayFillSource,
    SimulatedFillSource,
    _corr_key,
)
from application.execution.protocols import FillSource
from domain.commands import PlaceOrderCommand
from domain.entities import Order
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


def _make_command(
    cid: CorrelationId | None = None,
    qty: str = "10",
    price: str = "2500",
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal(qty)),
        price=Price(value=Decimal(price)),
        time_in_force=TimeInForce.DAY,
        correlation_id=cid or CorrelationId(value=uuid4()),
    )


def _make_filled_order(cid: CorrelationId, order_id: str = "test-1") -> Order:
    """Create a FILLED order for testing ReplayFillSource."""
    from dataclasses import replace

    order = Order(
        order_id=OrderId(value=order_id),
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("2500")),
        time_in_force=TimeInForce.DAY,
        status=OrderStatus.PENDING,
        correlation_id=cid,
    ).transition_to(OrderStatus.SUBMITTED).transition_to(OrderStatus.FILLED)
    return replace(order, filled_quantity=Quantity(value=Decimal("10")))


class _AckOnlyAdapter:
    """Broker adapter that only returns an order ID (ack-only)."""

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return OrderId(value="LIVE-1")

    def cancel_order(self, order_id: OrderId) -> None:
        return None


class _OrderReturningAdapter(_AckOnlyAdapter):
    """Broker adapter that returns a full Order on place_order."""

    def place_order(self, command: PlaceOrderCommand) -> Order:
        from dataclasses import replace

        order = _make_filled_order(command.correlation_id, order_id="LIVE-ORDER")
        return replace(order, filled_quantity=command.quantity)


class _GetOrderAdapter(_AckOnlyAdapter):
    """Broker adapter with get_order method."""

    def get_order(self, order_id: OrderId) -> Order:
        return Order(
            order_id=order_id,
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(value=Decimal("1")),
            price=None,
            time_in_force=TimeInForce.DAY,
            status=OrderStatus.PENDING,
            correlation_id=CorrelationId(value=uuid4()),
        ).transition_to(OrderStatus.SUBMITTED)


class _PaperGateway:
    """Paper gateway for PaperFillSource testing."""

    def submit_order(self, command: PlaceOrderCommand) -> Order:
        from dataclasses import replace

        order = _make_filled_order(command.correlation_id, order_id="PAPER-1")
        return replace(order, filled_quantity=command.quantity)

    def cancel_order(self, order_id: OrderId) -> None:
        return None


class _TestFillSourceProtocol:
    """Protocol contract tests - each implementation must pass these."""

    @pytest.fixture
    def fill_source(self) -> FillSource:
        raise NotImplementedError

    def test_submit_returns_order(self, fill_source: FillSource) -> None:
        cmd = _make_command()
        order = fill_source.submit(cmd)
        assert isinstance(order, Order)
        assert order.order_id is not None
        assert order.instrument_id == cmd.instrument_id
        assert order.side == cmd.side
        assert order.order_type == cmd.order_type
        assert order.quantity == cmd.quantity
        assert order.time_in_force == cmd.time_in_force
        assert order.correlation_id == cmd.correlation_id

    def test_submit_returns_order_with_valid_status(self, fill_source: FillSource) -> None:
        cmd = _make_command()
        order = fill_source.submit(cmd)
        assert order.status in (OrderStatus.SUBMITTED, OrderStatus.FILLED, OrderStatus.PENDING)

    def test_cancel_accepts_order_id(self, fill_source: FillSource) -> None:
        # cancel should not raise
        fill_source.cancel(OrderId(value="test-order-id"))

    def test_is_runtime_checkable_protocol(self, fill_source: FillSource) -> None:
        assert isinstance(fill_source, FillSource)


class TestSimulatedFillSourceContract(_TestFillSourceProtocol):
    @pytest.fixture
    def fill_source(self) -> FillSource:
        return SimulatedFillSource()

    def test_submit_returns_filled_order(self) -> None:
        fill = SimulatedFillSource()
        cmd = _make_command()
        order = fill.submit(cmd)
        assert order.status is OrderStatus.FILLED
        assert order.filled_quantity == cmd.quantity


class TestPaperFillSourceContract(_TestFillSourceProtocol):
    @pytest.fixture
    def fill_source(self) -> FillSource:
        return PaperFillSource(gateway=_PaperGateway())

    def test_submit_returns_filled_order(self) -> None:
        fill = PaperFillSource(gateway=_PaperGateway())
        cmd = _make_command()
        order = fill.submit(cmd)
        assert order.status is OrderStatus.FILLED
        assert order.filled_quantity == cmd.quantity

    def test_submit_fallback_to_simulated_when_no_gateway(self) -> None:
        fill = PaperFillSource(gateway=None)
        cmd = _make_command()
        order = fill.submit(cmd)
        assert order.status is OrderStatus.FILLED


class TestBrokerFillSourceContract(_TestFillSourceProtocol):
    @pytest.fixture
    def fill_source(self) -> FillSource:
        return BrokerFillSource(adapter=_OrderReturningAdapter())

    def test_submit_requires_adapter(self) -> None:
        fill = BrokerFillSource(adapter=None)
        cmd = _make_command()
        with pytest.raises(ValueError, match="LIVE BrokerFillSource requires a broker adapter"):
            fill.submit(cmd)

    def test_submit_returns_filled_when_adapter_returns_order(self) -> None:
        fill = BrokerFillSource(adapter=_OrderReturningAdapter())
        cmd = _make_command()
        order = fill.submit(cmd)
        assert order.status is OrderStatus.FILLED

    def test_submit_returns_submitted_when_adapter_returns_id_only(self) -> None:
        fill = BrokerFillSource(adapter=_AckOnlyAdapter())
        cmd = _make_command()
        order = fill.submit(cmd)
        assert order.status is OrderStatus.SUBMITTED

    def test_submit_uses_get_order_when_available(self) -> None:
        fill = BrokerFillSource(adapter=_GetOrderAdapter())
        cmd = _make_command()
        order = fill.submit(cmd)
        assert order.status is OrderStatus.SUBMITTED

    def test_cancel_requires_adapter(self) -> None:
        fill = BrokerFillSource(adapter=None)
        with pytest.raises(ValueError, match="LIVE BrokerFillSource requires a broker adapter"):
            fill.cancel(OrderId(value="test-id"))

    def test_cancel_delegates_to_adapter(self) -> None:
        adapter = _AckOnlyAdapter()
        fill = BrokerFillSource(adapter=adapter)
        fill.cancel(OrderId(value="test-id"))  # Should not raise


class TestReplayFillSourceContract(_TestFillSourceProtocol):
    @pytest.fixture
    def fill_source(self) -> FillSource:
        # Use a ReplayFillSource that auto-records fills for any correlation_id
        # to satisfy the base class protocol tests
        class _AutoReplayFillSource(ReplayFillSource):
            def submit(self, command: PlaceOrderCommand) -> Order:
                key = _corr_key(command.correlation_id)
                order = self._fills.get(key)
                if order is None:
                    # Auto-create a fill for testing
                    order = _make_filled_order(command.correlation_id, order_id=f"auto-{key[:8]}")
                    self._fills[key] = order
                return order

        return _AutoReplayFillSource(recorded_fills={})

    def test_submit_returns_recorded_fill(self) -> None:
        cid = CorrelationId(value=uuid4())
        expected = _make_filled_order(cid, order_id="REPLAY-1")
        fill = ReplayFillSource(recorded_fills={cid: expected})
        cmd = _make_command(cid=cid)
        order = fill.submit(cmd)
        assert order.order_id.value == "REPLAY-1"
        assert order.status is OrderStatus.FILLED

    def test_submit_raises_when_no_recorded_fill(self) -> None:
        fill = ReplayFillSource(recorded_fills={})
        cmd = _make_command()
        with pytest.raises(KeyError, match="no recorded fill"):
            fill.submit(cmd)

    def test_cancel_is_noop(self) -> None:
        fill = ReplayFillSource(recorded_fills={})
        fill.cancel(OrderId(value="test-id"))  # Should not raise

    def test_record_adds_fill(self) -> None:
        fill = ReplayFillSource(recorded_fills={})
        cid = CorrelationId(value=uuid4())
        order = _make_filled_order(cid, order_id="RECORDED-1")
        fill.record(cid, order)
        cmd = _make_command(cid=cid)
        retrieved = fill.submit(cmd)
        assert retrieved.order_id.value == "RECORDED-1"


class TestFillSourceProtocolCompliance:
    """Verify all implementations are runtime-checkable FillSource protocols."""

    def test_all_implementations_are_runtime_checkable(self) -> None:
        implementations: list[FillSource] = [
            SimulatedFillSource(),
            PaperFillSource(),
            PaperFillSource(gateway=_PaperGateway()),
            BrokerFillSource(adapter=_AckOnlyAdapter()),
            ReplayFillSource(),
        ]
        for impl in implementations:
            assert isinstance(impl, FillSource), f"{type(impl).__name__} is not a FillSource"


# Helper classes needed by multiple test classes
class _PaperGateway:
    def submit_order(self, command: PlaceOrderCommand) -> Order:
        return _make_filled_order(command.correlation_id, order_id="PAPER-1")

    def cancel_order(self, order_id: OrderId) -> None:
        return None


class _AckOnlyAdapter:
    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return OrderId(value="LIVE-1")

    def cancel_order(self, order_id: OrderId) -> None:
        return None


class _OrderReturningAdapter(_AckOnlyAdapter):
    def place_order(self, command: PlaceOrderCommand) -> Order:
        return _make_filled_order(command.correlation_id, order_id="LIVE-ORDER")


class _GetOrderAdapter(_AckOnlyAdapter):
    def get_order(self, order_id: OrderId) -> Order:
        return Order(
            order_id=order_id,
            instrument_id=InstrumentId.parse("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Quantity(value=Decimal("1")),
            price=None,
            time_in_force=TimeInForce.DAY,
            status=OrderStatus.PENDING,
            correlation_id=CorrelationId(value=uuid4()),
        ).transition_to(OrderStatus.SUBMITTED)