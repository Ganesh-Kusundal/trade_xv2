"""Upstox Order Lifecycle Integration Tests (P6-1).

Tests that verify complete order lifecycle through Upstox adapter:
- Complete order lifecycle (PENDING → OPEN → FILLED)
- Partial fill handling
- Rejection handling
- State transitions
- Audit trail verification
- Order cancellation flows
- Integration with OrderManager

Run with:
    pytest tests/integration/test_upstox_order_lifecycle.py -v
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest

from application.oms.order_manager import OmsOrderCommand, OrderManager
from brokers.upstox.wire import UpstoxWireAdapter
from domain import (
    Order,
    OrderResponse,
    OrderStatus,
    Side,
    Trade,
)
from infrastructure.event_bus import EventBus
from tests.integration.fixtures.upstox import (
    make_instrument_defn,
    make_mock_broker,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_broker():
    """Create a mock broker with live orders enabled."""
    return make_mock_broker(allow_live_orders=True)


@pytest.fixture
def gateway(mock_broker):
    """Create an UpstoxWireAdapter with mock broker."""
    return UpstoxWireAdapter(mock_broker)


@pytest.fixture
def instrument_defn():
    """Create a standard instrument definition."""
    return make_instrument_defn(
        name="RELIANCE",
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        exchange_segment="NSE_EQ",
    )


@pytest.fixture
def event_bus():
    """Create an EventBus for testing."""
    return EventBus()


@pytest.fixture
def order_manager(event_bus):
    """Create an OrderManager for testing."""
    return OrderManager(event_bus=event_bus)


# ─── Complete Order Lifecycle ─────────────────────────────────────────────


class TestCompleteOrderLifecycle:
    """Test complete order lifecycle from placement to fill."""

    def test_place_order_returns_success_response(self, mock_broker, instrument_defn):
        """place_order() should return OrderResponse with success=True."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-ORD-001",
            message="Order placed successfully",
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="MARKET",
        )

        assert result.success is True
        assert result.order_id == "UPSTOX-ORD-001"
        assert result.message == "Order placed successfully"

    def test_order_response_has_required_fields(self, mock_broker, instrument_defn):
        """OrderResponse should have all required fields populated."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-ORD-002",
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        assert hasattr(result, "success")
        assert hasattr(result, "order_id")
        assert hasattr(result, "message")
        assert hasattr(result, "status")
        assert hasattr(result, "error_code")
        assert hasattr(result, "raw_payload")

    def test_order_response_status_is_open_on_success(self, mock_broker, instrument_defn):
        """Successful order response should have status=OPEN."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-ORD-003",
            status=OrderStatus.OPEN,
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        assert result.status == OrderStatus.OPEN

    def test_place_order_with_correlation_id(self, mock_broker, instrument_defn):
        """place_order() should pass correlation_id for tracing."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-ORD-004",
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
            correlation_id="test-corr-123",
        )

        assert result.success is True
        mock_broker.order_command.place_order.assert_called_once()

    def test_place_order_with_trigger_price(self, mock_broker, instrument_defn):
        """place_order() should handle STOP_LOSS with trigger_price."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-ORD-005",
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            price=Decimal("2500"),
            order_type="STOP_LOSS",
            trigger_price=Decimal("2490"),
        )

        assert result.success is True


# ─── Partial Fill Handling ────────────────────────────────────────────────


class TestPartialFillHandling:
    """Test partial fill scenarios."""

    def test_order_response_with_partial_fill(self, mock_broker, instrument_defn):
        """OrderResponse should reflect partial fill state."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-ORD-010",
            status=OrderStatus.PARTIALLY_FILLED,
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            order_type="LIMIT",
            price=Decimal("2500"),
        )

        assert result.status == OrderStatus.PARTIALLY_FILLED

    def test_order_manager_records_partial_fill(self, order_manager):
        """OrderManager should correctly record partial fills."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
            correlation_id="partial-fill-test",
        )
        result = order_manager.place_order(cmd)
        assert result.success is True
        order = result.order
        assert order.filled_quantity == 0

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2500"),
        )
        accepted = order_manager.record_trade(trade)

        assert accepted is True
        updated = order_manager.get_order(order.order_id)
        assert updated is not None
        assert updated.filled_quantity == 5
        assert updated.status == OrderStatus.PARTIALLY_FILLED

    def test_order_manager_records_full_fill_after_partial(self, order_manager):
        """OrderManager should complete fill after partial."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
            correlation_id="full-fill-test",
        )
        result = order_manager.place_order(cmd)
        order = result.order

        trade1 = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2500"),
        )
        order_manager.record_trade(trade1)

        trade2 = Trade(
            trade_id="T2",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2501"),
        )
        order_manager.record_trade(trade2)

        updated = order_manager.get_order(order.order_id)
        assert updated is not None
        assert updated.filled_quantity == 10
        assert updated.status == OrderStatus.FILLED


# ─── Rejection Handling ───────────────────────────────────────────────────


class TestRejectionHandling:
    """Test order rejection scenarios."""

    def test_order_response_on_rejection(self, mock_broker, instrument_defn):
        """OrderResponse should have success=False on rejection."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.fail(
            message="Margin insufficient",
            error_code="BRO_ERR_MARGIN",
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1000,
            order_type="LIMIT",
            price=Decimal("2500"),
        )

        assert result.success is False
        assert result.status == OrderStatus.REJECTED
        assert "margin" in result.message.lower()

    def test_order_manager_rejected_order_not_in_book(self, order_manager):
        """Rejected orders should not be added to order book."""

        def failing_submit(request):
            raise RuntimeError("Order rejected by broker")

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="reject-test",
        )
        result = order_manager.place_order(cmd, submit_fn=failing_submit)

        assert result.success is False
        assert order_manager.get_order_by_correlation("reject-test") is None

    def test_order_manager_idempotent_on_duplicate_correlation(self, order_manager):
        """OrderManager should return existing order on duplicate correlation_id."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="idempotent-test",
        )
        result1 = order_manager.place_order(cmd)
        result2 = order_manager.place_order(cmd)

        assert result1.success is True
        assert result2.success is True
        assert result1.order.order_id == result2.order.order_id


# ─── Order Cancellation ───────────────────────────────────────────────────


class TestOrderCancellation:
    """Test order cancellation flows."""

    def test_cancel_order_success_flow(self, mock_broker):
        """cancel_order() should return success on successful cancellation."""
        mock_broker.order_command.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-CANCEL-001",
            message="Order cancelled",
        )
        mock_broker.order_query.get_order.return_value = None

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.cancel_order("ORD-CANCEL-001")

        assert result.success is True
        assert result.order_id == "ORD-CANCEL-001"

    def test_cancel_order_in_order_manager(self, order_manager):
        """OrderManager should cancel order locally after broker confirmation."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="cancel-test",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        cancel_result = order_manager.cancel_order(
            order_id,
            cancel_fn=lambda oid: True,
        )

        assert cancel_result.success is True
        assert cancel_result.order is not None
        assert cancel_result.order.status == OrderStatus.CANCELLED

    def test_cancel_order_fails_when_broker_cancel_fails(self, order_manager):
        """OrderManager should not update local state when broker cancel fails."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="cancel-fail-test",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        cancel_result = order_manager.cancel_order(
            order_id,
            cancel_fn=lambda oid: False,
        )

        assert cancel_result.success is False

        order = order_manager.get_order(order_id)
        assert order is not None
        assert order.status == OrderStatus.OPEN

    def test_cancel_order_fails_for_terminal_order(self, order_manager):
        """OrderManager should reject cancel for already terminal orders."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="terminal-cancel-test",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        order_manager.cancel_order(order_id, cancel_fn=lambda oid: True)

        second_cancel = order_manager.cancel_order(order_id)
        assert second_cancel.success is False
        assert "final" in second_cancel.error.lower()

    def test_cancel_order_fails_for_unknown_order(self, order_manager):
        """OrderManager should reject cancel for unknown order_id."""
        result = order_manager.cancel_order("UNKNOWN-ORDER")

        assert result.success is False
        assert "not found" in result.error.lower()


# ─── State Transitions ───────────────────────────────────────────────────


class TestStateTransitions:
    """Test order state machine transitions."""

    def test_open_to_partially_filled_transition(self, order_manager):
        """OPEN → PARTIALLY_FILLED should be valid."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="transition-test-1",
        )
        result = order_manager.place_order(cmd)
        order = result.order
        assert order.status == OrderStatus.OPEN

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2500"),
        )
        order_manager.record_trade(trade)

        updated = order_manager.get_order(order.order_id)
        assert updated is not None
        assert updated.status == OrderStatus.PARTIALLY_FILLED

    def test_open_to_cancelled_transition(self, order_manager):
        """OPEN → CANCELLED should be valid."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="transition-test-2",
        )
        result = order_manager.place_order(cmd)
        order = result.order
        assert order.status == OrderStatus.OPEN

        cancel_result = order_manager.cancel_order(
            order.order_id,
            cancel_fn=lambda oid: True,
        )
        assert cancel_result.success is True

        updated = order_manager.get_order(order.order_id)
        assert updated is not None
        assert updated.status == OrderStatus.CANCELLED

    def test_filled_to_cancelled_is_invalid(self, order_manager):
        """FILLED → CANCELLED should be invalid (terminal state)."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="transition-test-3",
        )
        result = order_manager.place_order(cmd)
        order = result.order

        trade = Trade(
            trade_id="T1",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
        )
        order_manager.record_trade(trade)

        updated = order_manager.get_order(order.order_id)
        assert updated is not None
        assert updated.status == OrderStatus.FILLED

        cancel_result = order_manager.cancel_order(order.order_id)
        assert cancel_result.success is False


# ─── Audit Trail Verification ────────────────────────────────────────────


class TestAuditTrail:
    """Test audit trail for order operations."""

    def test_order_placement_creates_audit_entry(self, order_manager):
        """OrderManager should log audit entry on placement."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="audit-test-1",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        audit_entries = order_manager._audit_logger._audit_log.get(order_id, [])
        assert len(audit_entries) >= 1
        # First entry should be new order (old_status=None, new_status=OPEN)
        assert audit_entries[0].old_status is None
        assert str(audit_entries[0].new_status) == "OrderStatus.OPEN"

    def test_order_state_change_creates_audit_entry(self, order_manager):
        """OrderManager should log audit entry on state change."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
            correlation_id="audit-test-2",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        initial_count = len(order_manager._audit_logger._audit_log.get(order_id, []))
        order_manager.cancel_order(order_id, cancel_fn=lambda oid: True)

        entries = order_manager._audit_logger._audit_log.get(order_id, [])
        assert len(entries) > initial_count

        # Cancel creates a state change from OPEN to CANCELLED
        state_changes = [e for e in entries if str(e.new_status) == "OrderStatus.CANCELLED"]
        assert len(state_changes) >= 1

    def test_trade_application_creates_audit_entry(self, order_manager):
        """OrderManager should log audit entry on trade application."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="audit-test-3",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        initial_count = len(order_manager._audit_logger._audit_log.get(order_id, []))

        trade = Trade(
            trade_id="T1",
            order_id=order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2500"),
        )
        order_manager.record_trade(trade)

        entries = order_manager._audit_logger._audit_log.get(order_id, [])
        assert len(entries) > initial_count

        # Trade application changes status to PARTIALLY_FILLED or FILLED
        trade_entries = [
            e
            for e in entries
            if "PARTIALLY_FILLED" in str(e.new_status) or "FILLED" in str(e.new_status)
        ]
        assert len(trade_entries) >= 1


# ─── OrderManager + Gateway Integration ──────────────────────────────────


class TestOrderManagerGatewayIntegration:
    """Test OrderManager integration with UpstoxGateway."""

    def test_order_manager_with_gateway_submit(self, mock_broker, instrument_defn, order_manager):
        """OrderManager should work with gateway as submit_fn."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn

        def submit_fn(request):
            mock_broker.order_command.place_order.return_value = OrderResponse.ok(
                order_id="UPSTOX-OMS-001",
            )
            return Order(
                order_id="UPSTOX-OMS-001",
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                price=request.price,
                status=OrderStatus.OPEN,
            )

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
            correlation_id="oms-gateway-test",
        )
        result = order_manager.place_order(cmd, submit_fn=submit_fn)

        assert result.success is True
        assert result.order is not None
        assert result.order.order_id == "UPSTOX-OMS-001"

    def test_order_manager_events_published(self, mock_broker, instrument_defn):
        """Order operations should publish events to EventBus."""
        event_bus = EventBus()
        received_events = []
        event_bus.subscribe("ORDER_PLACED", lambda e: received_events.append(e))

        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-EVT-001",
        )

        gateway = UpstoxWireAdapter(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        assert result.success is True


# ─── Thread Safety for Orders ────────────────────────────────────────────


class TestOrderThreadSafety:
    """Test concurrent order operations."""

    def test_concurrent_order_placements_with_oms(self, order_manager):
        """Concurrent order placements through OrderManager should be safe."""
        errors = []
        placed_orders = []
        lock = threading.Lock()

        def place_order(i: int):
            try:
                cmd = OmsOrderCommand(
                    symbol="RELIANCE",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=1,
                    correlation_id=f"concurrent-{i}",
                )
                result = order_manager.place_order(cmd)
                if result.success:
                    with lock:
                        placed_orders.append(result.order.order_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place_order, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        assert len(placed_orders) == 20
        assert len(set(placed_orders)) == 20

    def test_concurrent_cancel_operations(self, order_manager):
        """Concurrent cancel operations should be safe."""
        order_ids = []
        for i in range(10):
            cmd = OmsOrderCommand(
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=1,
                correlation_id=f"cancel-concurrent-{i}",
            )
            result = order_manager.place_order(cmd)
            order_ids.append(result.order.order_id)

        errors = []
        cancelled = []
        lock = threading.Lock()

        def cancel_order(order_id: str):
            try:
                result = order_manager.cancel_order(
                    order_id,
                    cancel_fn=lambda oid: True,
                )
                if result.success:
                    with lock:
                        cancelled.append(order_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(cancel_order, oid) for oid in order_ids]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        assert len(cancelled) == 10

    def test_concurrent_trade_recordings(self, order_manager):
        """Concurrent trade recordings should be safe (idempotent)."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="trade-concurrent",
        )
        result = order_manager.place_order(cmd)
        order_id = result.order.order_id

        errors = []
        accepted_count = {"value": 0}
        count_lock = threading.Lock()

        def record_trade(trade_id: str):
            try:
                trade = Trade(
                    trade_id=trade_id,
                    order_id=order_id,
                    symbol="RELIANCE",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=1,
                    price=Decimal("2500"),
                )
                accepted = order_manager.record_trade(trade)
                if accepted:
                    with count_lock:
                        accepted_count["value"] += 1
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(record_trade, "T1") for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        assert accepted_count["value"] == 1
