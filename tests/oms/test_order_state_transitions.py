"""Comprehensive order state machine transition tests.

These tests verify that OrderManager enforces valid order status transitions
when enforce_state_transitions=True (the new default), and allows invalid
transitions when explicitly set to False (backward compatibility).

Valid transitions (from ORDER_STATUS_TRANSITIONS):
    OPEN → PARTIALLY_FILLED, CANCELLED, REJECTED, EXPIRED
    PARTIALLY_FILLED → FILLED, CANCELLED, REJECTED
    FILLED → (terminal, no transitions)
    CANCELLED → (terminal, no transitions)
    REJECTED → (terminal, no transitions)
    EXPIRED → (terminal, no transitions)
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain import Order, OrderStatus, OrderType, ProductType, Side
from brokers.common.state_machine import IllegalTransitionError
from infrastructure.event_bus import EventBus
from application.oms.order_manager import OmsOrderCommand, OrderManager


def _make_order(
    order_id: str = "OM-test123",
    status: OrderStatus = OrderStatus.OPEN,
    correlation_id: str = "test-corr-1",
) -> Order:
    """Helper to create an Order with minimal fields."""
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE_EQ",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=Decimal("2500"),
        product_type=ProductType.INTRADAY,
        status=status,
        timestamp=datetime.now(timezone.utc),
        correlation_id=correlation_id,
    )


class TestOrderStateTransitionsEnforcedByDefault:
    """Test that enforce_state_transitions=True is the default (P0.5)."""

    def test_default_enforcement_is_true(self) -> None:
        """OrderManager should enforce state transitions by default."""
        om = OrderManager()
        assert om._enforce_state_transitions is True

    def test_explicit_false_disables_enforcement(self) -> None:
        """Backward compatibility: explicitly passing False should disable enforcement."""
        om = OrderManager(enforce_state_transitions=False)
        assert om._enforce_state_transitions is False

    def test_explicit_true_enables_enforcement(self) -> None:
        om = OrderManager(enforce_state_transitions=True)
        assert om._enforce_state_transitions is True


class TestValidTransitionsWithEnforcement:
    """Test that all valid transitions work when enforcement is ON."""

    @pytest.fixture
    def order_manager(self) -> OrderManager:
        return OrderManager(enforce_state_transitions=True)

    def test_open_to_partially_filled(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.OPEN)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.PARTIALLY_FILLED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.PARTIALLY_FILLED

    def test_open_to_cancelled(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.OPEN)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.CANCELLED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.CANCELLED

    def test_open_to_rejected(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.OPEN)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.REJECTED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.REJECTED

    def test_open_to_expired(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.OPEN)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.EXPIRED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.EXPIRED

    def test_partially_filled_to_filled(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.PARTIALLY_FILLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.FILLED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.FILLED

    def test_partially_filled_to_cancelled(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.PARTIALLY_FILLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.CANCELLED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.CANCELLED

    def test_partially_filled_to_rejected(self, order_manager: OrderManager) -> None:
        order = _make_order(status=OrderStatus.PARTIALLY_FILLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.REJECTED)
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).status == OrderStatus.REJECTED

    def test_same_status_update_is_allowed(self, order_manager: OrderManager) -> None:
        """Updating an order with the same status should not raise."""
        from dataclasses import replace
        
        order = _make_order(status=OrderStatus.OPEN)
        order_manager.upsert_order(order)

        # Update with same status (e.g., price update)
        updated = replace(order, price=Decimal("2600"))
        order_manager.upsert_order(updated)

        assert order_manager.get_order(order.order_id).price == Decimal("2600")


class TestInvalidTransitionsWithEnforcement:
    """Test that invalid transitions are rejected when enforcement is ON."""

    @pytest.fixture
    def order_manager(self) -> OrderManager:
        return OrderManager(enforce_state_transitions=True)

    def test_filled_to_open_raises(self, order_manager: OrderManager) -> None:
        """Terminal state FILLED cannot transition back to OPEN."""
        order = _make_order(status=OrderStatus.FILLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.OPEN)
        with pytest.raises(IllegalTransitionError) as exc_info:
            order_manager.upsert_order(updated)

        assert exc_info.value.from_state == OrderStatus.FILLED
        assert exc_info.value.to_state == OrderStatus.OPEN

    def test_cancelled_to_open_raises(self, order_manager: OrderManager) -> None:
        """Terminal state CANCELLED cannot transition back to OPEN."""
        order = _make_order(status=OrderStatus.CANCELLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.OPEN)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_rejected_to_open_raises(self, order_manager: OrderManager) -> None:
        """Terminal state REJECTED cannot transition back to OPEN."""
        order = _make_order(status=OrderStatus.REJECTED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.OPEN)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_expired_to_open_raises(self, order_manager: OrderManager) -> None:
        """Terminal state EXPIRED cannot transition back to OPEN."""
        order = _make_order(status=OrderStatus.EXPIRED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.OPEN)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_open_to_filled_skipping_partially_raises(self, order_manager: OrderManager) -> None:
        """OPEN cannot directly transition to FILLED (must go through PARTIALLY_FILLED)."""
        order = _make_order(status=OrderStatus.OPEN)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.FILLED)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_filled_to_partially_filled_raises(self, order_manager: OrderManager) -> None:
        """Terminal state FILLED cannot transition to PARTIALLY_FILLED."""
        order = _make_order(status=OrderStatus.FILLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.PARTIALLY_FILLED)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_cancelled_to_filled_raises(self, order_manager: OrderManager) -> None:
        """Terminal state CANCELLED cannot transition to FILLED."""
        order = _make_order(status=OrderStatus.CANCELLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.FILLED)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_filled_to_cancelled_raises(self, order_manager: OrderManager) -> None:
        """Terminal state FILLED cannot transition to CANCELLED."""
        order = _make_order(status=OrderStatus.FILLED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.CANCELLED)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_rejected_to_cancelled_raises(self, order_manager: OrderManager) -> None:
        """Terminal state REJECTED cannot transition to CANCELLED."""
        order = _make_order(status=OrderStatus.REJECTED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.CANCELLED)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)

    def test_expired_to_rejected_raises(self, order_manager: OrderManager) -> None:
        """Terminal state EXPIRED cannot transition to REJECTED."""
        order = _make_order(status=OrderStatus.EXPIRED)
        order_manager.upsert_order(order)

        updated = order.with_status(OrderStatus.REJECTED)
        with pytest.raises(IllegalTransitionError):
            order_manager.upsert_order(updated)


class TestInvalidTransitionsAuditMode:
    """Test that invalid transitions are accepted (with warning) when enforcement is OFF."""

    @pytest.fixture
    def order_manager_audit(self) -> OrderManager:
        return OrderManager(enforce_state_transitions=False)

    def test_open_to_filled_accepted_in_audit_mode(
        self, order_manager_audit: OrderManager, caplog
    ) -> None:
        """OPEN → FILLED should be accepted in audit mode with a warning."""
        order = _make_order(status=OrderStatus.OPEN)
        order_manager_audit.upsert_order(order)

        updated = order.with_status(OrderStatus.FILLED)
        # Should NOT raise in audit mode
        order_manager_audit.upsert_order(updated)

        assert order_manager_audit.get_order(order.order_id).status == OrderStatus.FILLED
        # Verify warning was logged
        assert "illegal order status transition" in caplog.text.lower()

    def test_cancelled_to_open_accepted_in_audit_mode(
        self, order_manager_audit: OrderManager, caplog
    ) -> None:
        """CANCELLED → OPEN should be accepted in audit mode with a warning."""
        order = _make_order(status=OrderStatus.CANCELLED)
        order_manager_audit.upsert_order(order)

        updated = order.with_status(OrderStatus.OPEN)
        order_manager_audit.upsert_order(updated)

        assert order_manager_audit.get_order(order.order_id).status == OrderStatus.OPEN
        assert "illegal order status transition" in caplog.text.lower()

    def test_filled_to_cancelled_accepted_in_audit_mode(
        self, order_manager_audit: OrderManager, caplog
    ) -> None:
        """FILLED → CANCELLED should be accepted in audit mode with a warning."""
        order = _make_order(status=OrderStatus.FILLED)
        order_manager_audit.upsert_order(order)

        updated = order.with_status(OrderStatus.CANCELLED)
        order_manager_audit.upsert_order(updated)

        assert order_manager_audit.get_order(order.order_id).status == OrderStatus.CANCELLED
        assert "illegal order status transition" in caplog.text.lower()


class TestStateTransitionsWithPlaceOrder:
    """Test state transitions through the place_order API."""

    def test_place_order_creates_open_order(self) -> None:
        """place_order should create an order with OPEN status."""
        event_bus = MagicMock(spec=EventBus)
        om = OrderManager(event_bus=event_bus, enforce_state_transitions=True)

        request = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE_EQ",
            side=Side.BUY,
            quantity=10,
            correlation_id="test-place-1",
        )

        result = om.place_order(request)
        assert result.success is True
        assert result.order is not None
        assert result.order.status == OrderStatus.OPEN

    def test_place_order_then_upsert_to_partially_filled(self) -> None:
        """Place order, then transition to PARTIALLY_FILLED via upsert."""
        event_bus = MagicMock(spec=EventBus)
        om = OrderManager(event_bus=event_bus, enforce_state_transitions=True)

        request = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE_EQ",
            side=Side.BUY,
            quantity=10,
            correlation_id="test-place-2",
        )

        result = om.place_order(request)
        order = result.order

        # Transition to PARTIALLY_FILLED
        updated = order.with_status(OrderStatus.PARTIALLY_FILLED)
        om.upsert_order(updated)

        assert om.get_order(order.order_id).status == OrderStatus.PARTIALLY_FILLED

    def test_place_order_then_invalid_transition_rejected(self) -> None:
        """Place order, then attempt invalid transition OPEN → FILLED."""
        event_bus = MagicMock(spec=EventBus)
        om = OrderManager(event_bus=event_bus, enforce_state_transitions=True)

        request = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE_EQ",
            side=Side.BUY,
            quantity=10,
            correlation_id="test-place-3",
        )

        result = om.place_order(request)
        order = result.order

        # Invalid transition: OPEN → FILLED (skipping PARTIALLY_FILLED)
        updated = order.with_status(OrderStatus.FILLED)
        with pytest.raises(IllegalTransitionError):
            om.upsert_order(updated)


class TestStateTransitionsThreadSafety:
    """Test that state transitions are thread-safe."""

    def test_concurrent_upserts_no_corruption(self) -> None:
        """Concurrent upserts should not corrupt state machine."""
        om = OrderManager(enforce_state_transitions=True)
        order = _make_order(status=OrderStatus.OPEN)
        om.upsert_order(order)

        errors = []

        def try_transition(target_status: OrderStatus) -> None:
            try:
                updated = order.with_status(target_status)
                om.upsert_order(updated)
            except IllegalTransitionError:
                pass  # Expected for invalid transitions
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=try_transition, args=(OrderStatus.PARTIALLY_FILLED,)),
            threading.Thread(target=try_transition, args=(OrderStatus.CANCELLED,)),
            threading.Thread(target=try_transition, args=(OrderStatus.REJECTED,)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No unexpected exceptions
        assert len(errors) == 0
        # Order should be in one of the valid terminal states or PARTIALLY_FILLED
        final_status = om.get_order(order.order_id).status
        assert final_status in {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }


class TestStateMachineLifecycle:
    """Test state machine lifecycle and initialization."""

    def test_state_machine_created_on_first_upsert(self) -> None:
        """State machine should be created when order is first upserted."""
        om = OrderManager(enforce_state_transitions=True)
        order = _make_order(status=OrderStatus.OPEN)

        assert order.order_id not in om._state_machines
        om.upsert_order(order)
        assert order.order_id in om._state_machines

    def test_state_machine_tracks_correct_state(self) -> None:
        """State machine should track the current order status."""
        om = OrderManager(enforce_state_transitions=True)
        order = _make_order(status=OrderStatus.OPEN)
        om.upsert_order(order)

        sm = om._state_machines[order.order_id]
        assert sm.state == OrderStatus.OPEN

        # Transition to PARTIALLY_FILLED
        updated = order.with_status(OrderStatus.PARTIALLY_FILLED)
        om.upsert_order(updated)

        assert sm.state == OrderStatus.PARTIALLY_FILLED

    def test_new_order_inherits_status_from_order(self) -> None:
        """New order's state machine should start from the order's status."""
        om = OrderManager(enforce_state_transitions=True)
        order = _make_order(status=OrderStatus.PARTIALLY_FILLED)
        om.upsert_order(order)

        sm = om._state_machines[order.order_id]
        assert sm.state == OrderStatus.PARTIALLY_FILLED
        # Should be able to transition to FILLED
        assert sm.can_transition_to(OrderStatus.FILLED)
        # Should NOT be able to transition back to OPEN
        assert not sm.can_transition_to(OrderStatus.OPEN)
