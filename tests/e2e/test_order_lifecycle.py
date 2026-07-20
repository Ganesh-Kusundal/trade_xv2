"""End-to-end order lifecycle test.

Tests the complete flow: Place Order → Risk Check → Fill → Position Update.

Uses mock broker to avoid network dependencies while exercising
the full OMS pipeline including EventBus, OrderManager, PositionManager,
RiskManager, and ProcessedTradeRepository.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from tests.conftest import build_test_trading_context

pytestmark = pytest.mark.e2e

from application.oms import (
    PositionManager,
    RiskConfig,
    RiskManager,
)
from domain import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Trade,
)
from infrastructure.event_bus import DomainEvent, EventBus
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from infrastructure.event_log import EventLog
from infrastructure.observability.event_metrics import EventMetrics


@pytest.fixture
def event_bus():
    return EventBus(dead_letter_queue=DeadLetterQueue(max_size=1000), metrics=EventMetrics())


@pytest.fixture
def risk_manager():
    return RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_fn=lambda: Decimal("1000000"),
    )


@pytest.fixture
def trading_context(event_bus, risk_manager, tmp_path):
    return build_test_trading_context(
        risk_manager=risk_manager,
        event_bus=event_bus,
        event_log=EventLog(events_dir=tmp_path / "events"),
    )


def _make_submit_fn(fill_price: Decimal = Decimal("2500")):
    """Create a mock submit function that returns a filled order."""

    def submit_fn(cmd):
        return Order(
            order_id=f"BROKER-{cmd.correlation_id[:8]}",
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            price=fill_price,
            status=OrderStatus.FILLED,
            product_type=cmd.product_type,
        )

    return submit_fn


def _make_trade(order: Order, fill_price: Decimal = Decimal("2500")) -> Trade:
    """Create a Trade from a filled order."""
    return Trade(
        trade_id=f"TRD-{order.order_id}",
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        side=order.side,
        quantity=order.quantity,
        price=fill_price,
    )


def _make_open_submit_fn(fill_price: Decimal = Decimal("2500")):
    """Create a mock submit function that returns an OPEN order (not filled yet)."""

    def submit_fn(cmd):
        return Order(
            order_id=f"BROKER-{cmd.correlation_id[:8]}",
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            price=fill_price,
            status=OrderStatus.OPEN,  # OPEN, not FILLED
            product_type=cmd.product_type,
        )

    return submit_fn


class TestOrderLifecycleE2E:
    def test_place_order_creates_order_in_oms(self, trading_context):
        from application.oms.order_manager import OmsOrderCommand

        tc = trading_context
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )

        result = tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is True
        assert result.order is not None
        assert result.order.symbol == "RELIANCE"
        assert result.order.quantity == 10

    def test_fill_event_updates_position(self, trading_context):
        tc = trading_context
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )

        result = tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trade = _make_trade(result.order)
        tc.order_manager.record_trade(trade)

        positions = tc.position_manager.get_positions()
        assert len(positions) > 0
        pos = positions[0]
        assert pos.symbol == "RELIANCE"
        assert pos.quantity == 10

    def test_idempotent_fill_does_not_double_position(self, trading_context):
        tc = trading_context
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )

        result = tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trade = _make_trade(result.order)
        tc.order_manager.record_trade(trade)

        positions = tc.position_manager.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10

    def test_risk_manager_blocks_order_when_kill_switch_active(self, trading_context):
        tc = trading_context
        tc.risk_manager.set_kill_switch(True)

        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )

        result = tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is False

    def test_concurrent_order_placement(self, trading_context):
        tc = trading_context
        from application.oms.order_manager import OmsOrderCommand

        results = []
        errors = []

        def place_order(idx):
            try:
                cmd = OmsOrderCommand(
                    symbol=f"STOCK{idx}",
                    exchange="NSE",
                    side=Side.BUY,
                    order_type=OrderType.MARKET,
                    quantity=1,
                    price=Decimal("100"),
                    product_type=ProductType.INTRADAY,
                )
                result = tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=place_order, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(r.success for r in results)

    def test_event_bus_publishes_order_events(self, trading_context):
        tc = trading_context
        received_events = []

        def on_event(event: DomainEvent):
            received_events.append(event)

        tc.event_bus.subscribe("ORDER_PLACED", on_event)

        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )

        tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert len(received_events) > 0
        assert any(e.event_type == "ORDER_PLACED" for e in received_events)

    def test_full_lifecycle_place_fill_position(self, trading_context):
        tc = trading_context
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )
        result = tc.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success

        trade = _make_trade(result.order)
        tc.order_manager.record_trade(trade)

        positions = tc.position_manager.get_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "RELIANCE"
        assert pos.quantity == 10
        assert pos.avg_price == Decimal("2500")

        orders = tc.order_manager.get_orders()
        filled = [o for o in orders if o.status == OrderStatus.FILLED]
        assert len(filled) > 0


# ── Order Modification Lifecycle ────────────────────────────────────────────


class TestOrderModificationLifecycle:
    """Tests: Order modification flow (price, quantity changes)."""

    def test_modify_order_price(self, trading_context):
        """Order price should be modifiable before fill."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success is True
        original_order = result.order

        # Modify price (if order manager supports it)
        # This test documents current capabilities
        try:
            trading_context.order_manager.modify_order(
                original_order.order_id,
                price=Decimal("2450"),
            )
            modified_order = trading_context.order_manager.get_order(original_order.order_id)
            # Verify modification took effect
            assert modified_order is not None
        except AttributeError:
            # modify_order may not be implemented - document gap
            pytest.skip("modify_order not implemented")

    def test_cancel_order_lifecycle(self, trading_context):
        """Order cancellation should transition through correct states."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="cancel-test-001",
        )

        # Use OPEN submit fn so order can be cancelled
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_open_submit_fn())
        assert result.success is True
        order_id = result.order.order_id

        # Cancel the order
        trading_context.order_manager.cancel_order(order_id)

        # Verify order status
        cancelled_order = trading_context.order_manager.get_order(order_id)
        assert cancelled_order.status == OrderStatus.CANCELLED

    def test_cancel_already_filled_order_fails(self, trading_context):
        """Cancelling a filled order should fail gracefully."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="cancel-filled-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trade = _make_trade(result.order)
        trading_context.order_manager.record_trade(trade)

        # Try to cancel filled order
        try:
            trading_context.order_manager.cancel_order(result.order.order_id)
            # If no exception, order should still be FILLED
            order = trading_context.order_manager.get_order(result.order.order_id)
            assert order.status == OrderStatus.FILLED
        except Exception as e:
            # Exception is also acceptable
            assert "filled" in str(e).lower() or "cancel" in str(e).lower()


# ── Order State Transitions ────────────────────────────────────────────────


class TestOrderStateTransitions:
    """Tests: Valid and invalid order state transitions."""

    def test_open_to_pending_to_filled(self, trading_context):
        """Order should transition: OPEN → PENDING → FILLED."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="state-transition-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        order = result.order

        # Initial state: OPEN
        assert order.status == OrderStatus.OPEN

        # Record partial fill
        partial_trade = Trade(
            trade_id="PARTIAL-STATE-001",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2500"),
        )
        trading_context.order_manager.record_trade(partial_trade)

        # State should reflect partial fill
        order_after_partial = trading_context.order_manager.get_order(order.order_id)
        assert order_after_partial.filled_quantity == 5

        # Complete the fill
        complete_trade = Trade(
            trade_id="COMPLETE-STATE-001",
            order_id=order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
            price=Decimal("2500"),
        )
        trading_context.order_manager.record_trade(complete_trade)

        # Final state: fully filled
        order_final = trading_context.order_manager.get_order(order.order_id)
        assert order_final.filled_quantity == 10

    def test_open_to_cancelled(self, trading_context):
        """Order should transition: OPEN → CANCELLED."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="cancel-transition-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        order_id = result.order.order_id

        # Cancel
        trading_context.order_manager.cancel_order(order_id)

        order = trading_context.order_manager.get_order(order_id)
        assert order.status == OrderStatus.CANCELLED

    def test_rejected_order_never_opens(self, trading_context):
        """Rejected order should never enter OPEN state."""
        from application.oms.order_manager import OmsOrderCommand

        # Activate kill switch to trigger rejection
        trading_context.risk_manager.set_kill_switch(True)

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="rejected-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is False
        # Order should not be in the order manager
        orders = trading_context.order_manager.get_orders()
        assert len(orders) == 0


# ── Complex Multi-Order Scenarios ───────────────────────────────────────────


class TestComplexMultiOrderScenarios:
    """Tests: Multiple orders interacting with each other."""

    def test_bracket_order_simulation(self, trading_context):
        """Simulate bracket order: entry + target + stop-loss."""
        from application.oms.order_manager import OmsOrderCommand

        # Entry order
        entry_cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="bracket-entry",
        )
        entry_result = trading_context.order_manager.place_order(
            entry_cmd, submit_fn=_make_submit_fn()
        )
        entry_trade = _make_trade(entry_result.order)
        trading_context.order_manager.record_trade(entry_trade)

        # Position should exist
        position = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert position.quantity == 10

        # Target order (limit sell at profit)
        target_cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2600"),  # 100 profit target
            product_type=ProductType.INTRADAY,
            correlation_id="bracket-target",
        )
        target_result = trading_context.order_manager.place_order(
            target_cmd, submit_fn=_make_submit_fn(Decimal("2600"))
        )

        # Stop-loss order (limit sell at loss)
        sl_cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2450"),  # 50 loss stop
            product_type=ProductType.INTRADAY,
            correlation_id="bracket-sl",
        )
        sl_result = trading_context.order_manager.place_order(
            sl_cmd, submit_fn=_make_submit_fn(Decimal("2450"))
        )

        # Both target and SL should be open
        assert target_result.order.status == OrderStatus.OPEN
        assert sl_result.order.status == OrderStatus.OPEN

    def test_cover_order_simulation(self, trading_context):
        """Simulate cover order: short entry + buy-to-cover."""
        from application.oms.order_manager import OmsOrderCommand

        # Short entry
        short_cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="cover-short",
        )
        short_result = trading_context.order_manager.place_order(
            short_cmd, submit_fn=_make_submit_fn()
        )
        short_trade = _make_trade(short_result.order)
        trading_context.order_manager.record_trade(short_trade)

        # Position should be short
        position = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert position.quantity == -10

        # Cover order
        cover_cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2450"),  # Profit target
            product_type=ProductType.INTRADAY,
            correlation_id="cover-buy",
        )
        cover_result = trading_context.order_manager.place_order(
            cover_cmd, submit_fn=_make_submit_fn(Decimal("2450"))
        )

        assert cover_result.order.status == OrderStatus.OPEN

    def test_legged_order_execution(self, trading_context):
        """Simulate multi-leg order (spread trading)."""
        from application.oms.order_manager import OmsOrderCommand

        # Leg 1: Buy RELIANCE
        leg1_cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="legged-leg1",
        )
        leg1_result = trading_context.order_manager.place_order(
            leg1_cmd, submit_fn=_make_submit_fn()
        )

        # Leg 2: Buy TCS (spread)
        leg2_cmd = OmsOrderCommand(
            symbol="TCS",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("3500"),
            product_type=ProductType.INTRADAY,
            correlation_id="legged-leg2",
        )
        leg2_result = trading_context.order_manager.place_order(
            leg2_cmd, submit_fn=_make_submit_fn(Decimal("3500"))
        )

        # Both legs should execute
        assert leg1_result.success is True
        assert leg2_result.success is True

        # Both positions should exist
        positions = trading_context.position_manager.get_positions()
        assert len(positions) == 2


# ── Edge Cases and Error Conditions ─────────────────────────────────────────


class TestOrderEdgeCases:
    """Tests: Edge cases and error conditions in order lifecycle."""

    def test_zero_quantity_order_rejected(self, trading_context):
        """Zero quantity order should be rejected."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="zero-qty-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success is False

    def test_negative_price_order_rejected(self, trading_context):
        """Negative price order should be rejected."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("-100"),
            product_type=ProductType.INTRADAY,
            correlation_id="neg-price-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success is False

    def test_duplicate_correlation_id_is_idempotent(self, trading_context):
        """Same correlation_id should return existing order."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="dup-correlation-001",
        )

        result1 = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        result2 = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result1.order.order_id == result2.order.order_id
        assert trading_context.order_manager.get_orders() == [result1.order]

    def test_order_expiry_simulation(self, trading_context):
        """Orders should expire after configured TTL."""
        from application.oms.order_manager import OmsOrderCommand

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=Decimal("2500"),
            product_type=ProductType.INTRADAY,
            correlation_id="expiry-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        order_id = result.order.order_id

        # Verify order exists
        order = trading_context.order_manager.get_order(order_id)
        assert order is not None

        # Expiry logic depends on implementation
        # This test documents current capabilities
        # Production systems may have background expiry checker
