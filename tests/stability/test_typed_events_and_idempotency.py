"""Tests for typed event classes and OMS idempotency (P5 Stability Engineering).

Verifies:
1. Typed event classes provide type-safe access to Order/Trade objects
2. Invalid payloads raise ValueError (fail-fast)
3. PositionManager idempotency prevents duplicate trade processing
4. EventBus idempotency + PositionManager idempotency work together
"""

from decimal import Decimal

import pytest

from domain.entities.order import Order
from domain.entities.trade import Trade
from domain.events.types import (
    OrderUpdatedEvent,
    TradeAppliedEvent,
    TradeFilledEvent,
)
from domain.types import Side
from infrastructure.event_bus.event_bus import DomainEvent, EventBus


class TestTypedEventClasses:
    """Test typed event wrappers provide compile-time safety."""

    def _make_order(self) -> Order:
        """Create a test Order."""
        from domain.types import OrderType

        return Order(
            order_id="O1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("1500.0"),
        )

    def _make_trade(self) -> Trade:
        """Create a test Trade."""
        return Trade(
            trade_id="T1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("1500.0"),
            order_id="O1",
        )

    def test_order_updated_event_type_safe_access(self):
        """OrderUpdatedEvent should provide type-safe Order access."""
        order = self._make_order()
        event = DomainEvent.now("ORDER_UPDATED", {"order": order})

        typed = OrderUpdatedEvent.from_domain_event(event)

        assert typed.order is order
        assert typed.order.order_id == "O1"
        assert typed.event_type == "ORDER_UPDATED"
        assert typed.event_id == event.event_id

    def test_trade_filled_event_type_safe_access(self):
        """TradeFilledEvent should provide type-safe Trade access."""
        trade = self._make_trade()
        event = DomainEvent.now("TRADE", {"trade": trade})

        typed = TradeFilledEvent.from_domain_event(event)

        assert typed.trade is trade
        assert typed.trade.trade_id == "T1"
        assert typed.event_type == "TRADE"

    def test_trade_applied_event_type_safe_access(self):
        """TradeAppliedEvent should provide type-safe Trade access."""
        trade = self._make_trade()
        event = DomainEvent.now("TRADE_APPLIED", {"trade": trade})

        typed = TradeAppliedEvent.from_domain_event(event)

        assert typed.trade is trade
        assert typed.trade.trade_id == "T1"
        assert typed.event_type == "TRADE_APPLIED"

    def test_order_updated_event_rejects_invalid_payload(self):
        """OrderUpdatedEvent should raise ValueError for invalid payload."""
        # Missing order key
        event = DomainEvent.now("ORDER_UPDATED", {"wrong_key": "value"})

        with pytest.raises(ValueError, match="ORDER_UPDATED event must contain Order"):
            OrderUpdatedEvent.from_domain_event(event)

    def test_trade_filled_event_rejects_invalid_payload(self):
        """TradeFilledEvent should raise ValueError for invalid payload."""
        # Missing trade key
        event = DomainEvent.now("TRADE", {"wrong_key": "value"})

        with pytest.raises(ValueError, match="TRADE event must contain Trade"):
            TradeFilledEvent.from_domain_event(event)

    def test_trade_applied_event_rejects_invalid_payload(self):
        """TradeAppliedEvent should raise ValueError for invalid payload."""
        # Wrong type in payload
        event = DomainEvent.now("TRADE_APPLIED", {"trade": "not a trade object"})

        with pytest.raises(ValueError, match="TRADE_APPLIED event must contain Trade"):
            TradeAppliedEvent.from_domain_event(event)

    def test_typed_event_preserves_correlation_id(self):
        """Typed events should preserve correlation_id from underlying event."""
        order = self._make_order()
        event = DomainEvent.now(
            "ORDER_UPDATED",
            {"order": order},
            correlation_id="test-correlation-123",
        )

        typed = OrderUpdatedEvent.from_domain_event(event)

        assert typed.correlation_id == "test-correlation-123"

    def test_typed_event_is_frozen(self):
        """Typed events should be immutable (frozen dataclass)."""
        order = self._make_order()
        event = DomainEvent.now("ORDER_UPDATED", {"order": order})
        typed = OrderUpdatedEvent.from_domain_event(event)

        with pytest.raises(Exception):  # FrozenInstanceError  # noqa: B017
            typed.order = None  # type: ignore[misc]


class TestPositionManagerIdempotency:
    """Test PositionManager prevents duplicate trade processing."""

    def _make_trade(self, trade_id: str = "T1") -> Trade:
        """Create a test Trade."""
        return Trade(
            trade_id=trade_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("1500.0"),
            order_id="O1",
        )

    def test_duplicate_trade_not_processed_twice(self):
        """PositionManager should skip duplicate trade_ids."""
        from application.oms.position_manager import PositionManager

        pm = PositionManager()

        trade = self._make_trade("T1")
        event = DomainEvent.now("TRADE_APPLIED", {"trade": trade})

        # First processing - should apply trade
        pm.on_trade_applied(event)
        position = pm.get_position("RELIANCE", "NSE")
        assert position.quantity == 10

        # Second processing (duplicate) - should skip
        pm.on_trade_applied(event)
        position = pm.get_position("RELIANCE", "NSE")
        assert position.quantity == 10  # Still 10, not 20

    def test_different_trades_both_processed(self):
        """PositionManager should process different trade_ids."""
        from application.oms.position_manager import PositionManager

        pm = PositionManager()

        trade1 = self._make_trade("T1")
        trade2 = self._make_trade("T2")

        event1 = DomainEvent.now("TRADE_APPLIED", {"trade": trade1})
        event2 = DomainEvent.now("TRADE_APPLIED", {"trade": trade2})

        pm.on_trade_applied(event1)
        pm.on_trade_applied(event2)

        position = pm.get_position("RELIANCE", "NSE")
        assert position.quantity == 20  # 10 + 10

    def test_idempotency_works_with_event_bus(self):
        """EventBus idempotency + PositionManager idempotency should work together."""
        from application.oms.position_manager import PositionManager

        bus = EventBus()
        pm = PositionManager(event_bus=bus)

        # Subscribe PositionManager
        bus.subscribe("TRADE_APPLIED", pm.on_trade_applied)

        trade = self._make_trade("T1")
        event = DomainEvent.now("TRADE_APPLIED", {"trade": trade})

        # Publish same event 3 times
        bus.publish(event)
        bus.publish(event)  # EventBus should skip (idempotency)
        bus.publish(event)  # EventBus should skip (idempotency)

        position = pm.get_position("RELIANCE", "NSE")
        assert position.quantity == 10  # Only processed once

    def test_idempotency_cache_does_not_block_valid_trades(self):
        """Idempotency should not prevent processing of new trades."""
        from application.oms.position_manager import PositionManager

        pm = PositionManager()

        # Process trade T1
        trade1 = self._make_trade("T1")
        event1 = DomainEvent.now("TRADE_APPLIED", {"trade": trade1})
        pm.on_trade_applied(event1)

        # Process trade T2 (different ID)
        trade2 = self._make_trade("T2")
        event2 = DomainEvent.now("TRADE_APPLIED", {"trade": trade2})
        pm.on_trade_applied(event2)

        position = pm.get_position("RELIANCE", "NSE")
        assert position.quantity == 20  # Both trades applied


class TestOMSHandlerErrorHandling:
    """Test OMS handlers gracefully handle invalid payloads."""

    def test_order_manager_handles_invalid_order_event(self):
        """OrderManager.on_order_update should log warning, not crash."""
        from application.oms.order_manager import OrderManager

        om = OrderManager()

        # Invalid event (no order in payload)
        event = DomainEvent.now("ORDER_UPDATED", {"wrong_key": "value"})

        # Should not raise exception
        om.on_order_update(event)

        # Order list should be empty (invalid event skipped)
        assert len(om.get_orders()) == 0

    def test_order_manager_handles_invalid_trade_event(self):
        """OrderManager.on_trade should log warning, not crash."""
        from application.oms.order_manager import OrderManager

        om = OrderManager()

        # Invalid event (no trade in payload)
        event = DomainEvent.now("TRADE", {"wrong_key": "value"})

        # Should not raise exception
        om.on_trade(event)

        # Just verify no crash - OrderManager API may vary
        assert True  # If we got here, test passed

    def test_position_manager_handles_invalid_trade_event(self):
        """PositionManager should log warning, not crash."""
        from application.oms.position_manager import PositionManager

        pm = PositionManager()

        # Invalid event (no trade in payload)
        event = DomainEvent.now("TRADE_APPLIED", {"wrong_key": "value"})

        # Should not raise exception
        pm.on_trade_applied(event)

        # No positions should be created
        assert len(pm.get_positions()) == 0
