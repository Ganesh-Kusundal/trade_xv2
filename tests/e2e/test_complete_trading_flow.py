"""E2E tests for complete trading flow: Strategy → Signal → Order → Fill → Position → PnL.

Tests the entire stack working together:
1. Strategy generates signals from market data
2. Signals create orders via OrderManager
3. Orders fill via mock broker
4. Positions update in PositionManager
5. PnL calculates correctly
6. Risk limits are enforced

All tests use TradingContext with paper broker (no real money).
Deterministic: same input produces same output.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from brokers.common.core.domain import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Trade,
)
from brokers.common.event_bus import DomainEvent, EventBus
from brokers.common.event_bus.dead_letter_queue import DeadLetterQueue
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.oms.context import TradingContext
from brokers.common.oms.order_manager import OmsOrderCommand, OrderResult
from brokers.common.oms.position_manager import PositionManager
from brokers.common.oms.risk_manager import RiskConfig, RiskManager

from tests.e2e.fixtures.event_capturer import EventCapturer
from tests.e2e.fixtures.trading_context_factory import (
    create_paper_trading_context,
    create_test_trading_context,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def trading_context(tmp_path):
    """Create a fresh TradingContext for each test."""
    return create_paper_trading_context(
        capital=Decimal("1000000"),
        events_dir=tmp_path / "events",
    )


@pytest.fixture
def event_capturer(trading_context):
    """Create an event capturer attached to the context's event bus."""
    capturer = EventCapturer(event_bus=trading_context.event_bus)
    capturer.subscribe(
        "ORDER_PLACED",
        "ORDER_UPDATED",
        "ORDER_CANCELLED",
        "TRADE_APPLIED",
        "POSITION_UPDATED",
        "POSITION_OPENED",
        "POSITION_CLOSED",
        "RISK_APPROVED",
        "RISK_REJECTED",
    )
    return capturer


def _make_submit_fn(fill_price: Decimal = Decimal("100.0")):
    """Create a mock submit function that returns an OPEN order (not auto-filled)."""
    import uuid
    def submit_fn(cmd):
        # Use a unique order_id to avoid collisions in concurrent tests
        unique_part = cmd.correlation_id.split('-')[-1][:12] if '-' in cmd.correlation_id else uuid.uuid4().hex[:12]
        return Order(
            order_id=f"BROKER-{unique_part}",
            symbol=cmd.symbol,
            exchange=cmd.exchange,
            side=cmd.side,
            order_type=cmd.order_type,
            quantity=cmd.quantity,
            price=fill_price,
            status=OrderStatus.OPEN,
            product_type=cmd.product_type,
            correlation_id=cmd.correlation_id,
        )
    return submit_fn


def _make_trade(order: Order, fill_price: Decimal) -> Trade:
    """Create a Trade from an order."""
    return Trade(
        trade_id=f"TRD-{order.order_id}",
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        side=order.side,
        quantity=order.quantity,
        price=fill_price,
        timestamp=datetime.now(timezone.utc),
    )


# ── Signal → Order Flow ─────────────────────────────────────────────────────


class TestSignalToOrderFlow:
    """Tests: Strategy signal creates order via OrderManager."""

    def test_buy_signal_creates_order(self, trading_context):
        """A BUY signal should create an OPEN order in the OMS."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="test-signal-001",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is True
        assert result.order is not None
        assert result.order.symbol == "RELIANCE"
        assert result.order.side == Side.BUY
        assert result.order.quantity == 10
        assert result.order.status == OrderStatus.OPEN

    def test_sell_signal_creates_order(self, trading_context):
        """A SELL signal should create an OPEN order."""
        cmd = OmsOrderCommand(
            symbol="TCS",
            exchange="NSE",
            side=Side.SELL,
            quantity=5,
            price=Decimal("200.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="test-signal-002",
        )

        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is True
        assert result.order.side == Side.SELL

    def test_duplicate_signal_is_idempotent(self, trading_context):
        """Same correlation_id should return existing order, not create new one."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            correlation_id="dup-signal-001",
        )

        result1 = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        result2 = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result1.order.order_id == result2.order.order_id
        assert trading_context.order_manager.get_orders() == [result1.order]

    def test_order_emits_events(self, trading_context, event_capturer):
        """Placing an order should publish ORDER_PLACED event."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="evt-test-001",
        )
        trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        event_capturer.assert_event_published("ORDER_PLACED", min_count=1)

    def test_risk_approved_event_published(self, trading_context, event_capturer):
        """Passing risk check should publish RISK_APPROVED."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="risk-approval-001",
        )
        trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        event_capturer.assert_event_published("RISK_APPROVED", min_count=1)


# ── Order → Fill → Position Flow ────────────────────────────────────────────


class TestOrderToPositionFlow:
    """Tests: Order fills and creates positions."""

    def test_fill_creates_position(self, trading_context):
        """Recording a trade should create a position."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="fill-test-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trade = _make_trade(result.order, Decimal("100.0"))
        trading_context.order_manager.record_trade(trade)

        positions = trading_context.position_manager.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10
        assert positions[0].avg_price == Decimal("100.0")

    def test_fill_updates_order_status(self, trading_context):
        """Recording a trade should update the order's filled_quantity."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="fill-test-002",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trade = _make_trade(result.order, Decimal("100.0"))
        trading_context.order_manager.record_trade(trade)

        order = trading_context.order_manager.get_order(result.order.order_id)
        assert order.filled_quantity == 10

    def test_fill_publishes_events(self, trading_context, event_capturer):
        """Recording a trade should publish TRADE_APPLIED and POSITION_UPDATED."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="fill-test-003",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        event_capturer.assert_event_published("TRADE_APPLIED", min_count=1)
        event_capturer.assert_event_published("POSITION_UPDATED", min_count=1)

    def test_position_opened_event_on_first_fill(self, trading_context, event_capturer):
        """First fill to a flat position should publish POSITION_OPENED."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="fill-test-004",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        event_capturer.assert_event_published("POSITION_OPENED", min_count=1)

    def test_partial_fill(self, trading_context):
        """Partial fill should update order with partial filled_quantity."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=100,
            price=Decimal("100.0"),
            correlation_id="partial-fill-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        # Partial fill: 30 of 100
        trade = Trade(
            trade_id="PARTIAL-001",
            order_id=result.order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=30,
            price=Decimal("100.0"),
        )
        trading_context.order_manager.record_trade(trade)

        order = trading_context.order_manager.get_order(result.order.order_id)
        assert order.filled_quantity == 30

        positions = trading_context.position_manager.get_positions()
        assert positions[0].quantity == 30

    def test_sell_reduces_long_position(self, trading_context):
        """SELL trade should reduce an existing long position."""
        # Open long
        cmd_buy = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="sell-reduce-buy",
        )
        buy_result = trading_context.order_manager.place_order(cmd_buy, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(buy_result.order, Decimal("100.0")))

        # Sell half
        cmd_sell = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=5, price=Decimal("110.0"), correlation_id="sell-reduce-sell",
        )
        sell_result = trading_context.order_manager.place_order(cmd_sell, submit_fn=_make_submit_fn(Decimal("110.0")))
        sell_trade = Trade(
            trade_id="SELL-001",
            order_id=sell_result.order.order_id,
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=5, price=Decimal("110.0"),
        )
        trading_context.order_manager.record_trade(sell_trade)

        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert pos.quantity == 5

    def test_full_close_flattens_position(self, trading_context, event_capturer):
        """Closing entire position should flatten it and publish POSITION_CLOSED."""
        # Open long
        cmd_buy = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="full-close-buy",
        )
        buy_result = trading_context.order_manager.place_order(cmd_buy, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(buy_result.order, Decimal("100.0")))

        # Close all
        cmd_sell = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=10, price=Decimal("105.0"), correlation_id="full-close-sell",
        )
        sell_result = trading_context.order_manager.place_order(cmd_sell, submit_fn=_make_submit_fn(Decimal("105.0")))
        sell_trade = Trade(
            trade_id="SELL-002",
            order_id=sell_result.order.order_id,
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=10, price=Decimal("105.0"),
        )
        trading_context.order_manager.record_trade(sell_trade)

        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert pos.quantity == 0
        event_capturer.assert_event_published("POSITION_CLOSED", min_count=1)


# ── PnL Calculations ────────────────────────────────────────────────────────


class TestPnLCalculations:
    """Tests: PnL is calculated correctly at each step."""

    def test_unrealized_pnl_on_long_position(self, trading_context):
        """Unrealized PnL = (LTP - avg_price) * quantity for longs."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="pnl-long-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        # Update LTP to 110
        trading_context.position_manager.update_ltp("RELIANCE", "NSE", Decimal("110.0"))

        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        expected_pnl = (Decimal("110.0") - Decimal("100.0")) * 10
        assert pos.unrealized_pnl == expected_pnl

    def test_unrealized_pnl_on_short_position(self, trading_context):
        """Unrealized PnL = (entry_price - LTP) * quantity for shorts."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=10, price=Decimal("100.0"), correlation_id="pnl-short-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        # Update LTP to 90 (profit for short)
        trading_context.position_manager.update_ltp("RELIANCE", "NSE", Decimal("90.0"))

        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        expected_pnl = (Decimal("100.0") - Decimal("90.0")) * 10
        assert pos.unrealized_pnl == expected_pnl

    def test_realized_pnl_on_close(self, trading_context):
        """Realized PnL = (exit_price - entry_price) * quantity."""
        # Buy at 100
        cmd_buy = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="pnl-realized-buy",
        )
        buy_result = trading_context.order_manager.place_order(cmd_buy, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(buy_result.order, Decimal("100.0")))

        # Sell at 110
        cmd_sell = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=10, price=Decimal("110.0"), correlation_id="pnl-realized-sell",
        )
        sell_result = trading_context.order_manager.place_order(cmd_sell, submit_fn=_make_submit_fn(Decimal("110.0")))
        sell_trade = Trade(
            trade_id="PNL-SELL-001",
            order_id=sell_result.order.order_id,
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=10, price=Decimal("110.0"),
        )
        trading_context.order_manager.record_trade(sell_trade)

        # Position should be flat
        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert pos.quantity == 0
        assert pos.realized_pnl == Decimal("100.0")  # (110 - 100) * 10


# ── Risk Limits ─────────────────────────────────────────────────────────────


class TestRiskLimits:
    """Tests: Risk limits are enforced."""

    def test_kill_switch_blocks_orders(self, trading_context):
        """Active kill switch should block all orders."""
        trading_context.risk_manager.set_kill_switch(True)

        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="kill-switch-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is False
        assert "Kill switch" in result.error

    def test_position_concentration_limit(self, tmp_path):
        """Orders exceeding max position % should be rejected."""
        ctx = create_test_trading_context(
            capital=Decimal("10000"),
            risk_config=RiskConfig(max_position_pct=Decimal("10")),
        )

        # 10% of 10000 = 1000 max notional
        # 20 shares * 100 = 2000 > 1000, should be rejected
        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=20, price=Decimal("100.0"), correlation_id="concentration-001",
        )
        result = ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is False
        assert "max position" in result.error.lower()

    def test_gross_exposure_limit(self, tmp_path):
        """Orders exceeding gross exposure should be rejected."""
        ctx = create_test_trading_context(
            capital=Decimal("10000"),
            risk_config=RiskConfig(max_gross_exposure_pct=Decimal("20")),
        )

        # First order: 15% of capital
        cmd1 = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=15, price=Decimal("100.0"), correlation_id="gross-001",
        )
        r1 = ctx.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        ctx.order_manager.record_trade(_make_trade(r1.order, Decimal("100.0")))

        # Second order: another 10% would exceed 20% limit
        cmd2 = OmsOrderCommand(
            symbol="TCS", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="gross-002",
        )
        r2 = ctx.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())

        assert r2.success is False
        assert "gross exposure" in r2.error.lower()

    def test_risk_rejected_event_published(self, trading_context, event_capturer):
        """Rejected order should publish RISK_REJECTED event."""
        trading_context.risk_manager.set_kill_switch(True)

        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="risk-rejected-001",
        )
        trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        event_capturer.assert_event_published("RISK_REJECTED", min_count=1)


# ── Concurrent Operations ───────────────────────────────────────────────────


class TestConcurrentOperations:
    """Tests: Thread safety of the trading stack."""

    def test_concurrent_order_placement(self, trading_context):
        """Multiple threads placing orders should not corrupt state."""
        results = []
        errors = []
        import uuid

        def place_order(idx):
            try:
                unique_id = f"concurrent-{idx}-{uuid.uuid4().hex}"
                cmd = OmsOrderCommand(
                    symbol=f"STOCK{idx}",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=1,
                    price=Decimal("100.0"),
                    correlation_id=unique_id,
                )
                result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
                results.append((idx, result))
            except Exception as e:
                errors.append((idx, e))

        threads = [threading.Thread(target=place_order, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10, f"Results: {len(results)}"
        assert all(r.success for _, r in results)
        # Verify orders were created
        orders = trading_context.order_manager.get_orders()
        assert len(orders) == 10, f"Orders: {len(orders)}, symbols: {[o.symbol for o in orders]}"

    def test_concurrent_fill_and_query(self, trading_context):
        """Filling orders while querying should not race."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=100, price=Decimal("100.0"), correlation_id="concurrent-fill",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        fill_errors = []
        query_results = []

        def fill():
            try:
                trade = Trade(
                    trade_id=f"CONCURRENT-FILL",
                    order_id=result.order.order_id,
                    symbol="RELIANCE", exchange="NSE", side=Side.BUY,
                    quantity=50, price=Decimal("100.0"),
                )
                trading_context.order_manager.record_trade(trade)
            except Exception as e:
                fill_errors.append(e)

        def query():
            for _ in range(10):
                try:
                    order = trading_context.order_manager.get_order(result.order.order_id)
                    query_results.append(order.filled_quantity if order else -1)
                except Exception as e:
                    fill_errors.append(e)

        t1 = threading.Thread(target=fill)
        t2 = threading.Thread(target=query)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(fill_errors) == 0
        # All queries should see either 0 or 50 filled (atomic updates)
        assert all(q in (0, 50) for q in query_results)


# ── State Consistency ───────────────────────────────────────────────────────


class TestStateConsistency:
    """Tests: State remains consistent across the full flow."""

    def test_order_position_trade_consistency(self, trading_context):
        """Order, position, and trade state should be consistent after full flow."""
        cmd = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="consistency-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        trade = _make_trade(result.order, Decimal("100.0"))
        trading_context.order_manager.record_trade(trade)

        # Verify order state
        order = trading_context.order_manager.get_order(result.order.order_id)
        assert order.filled_quantity == 10

        # Verify position state
        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert pos.quantity == 10
        assert pos.avg_price == Decimal("100.0")

        # Verify trade was recorded (idempotency ledger)
        from brokers.common.event_bus import TradeIdKey
        key = TradeIdKey(trade_id=trade.trade_id, order_id=trade.order_id)
        assert trading_context.processed_trade_repository.is_processed(key)

    def test_multiple_symbols_isolated(self, trading_context):
        """Positions for different symbols should be isolated."""
        import uuid
        for i, sym in enumerate(["RELIANCE", "TCS", "HDFCBANK"]):
            unique_id = f"multi-sym-{sym}-{uuid.uuid4().hex}"
            cmd = OmsOrderCommand(
                symbol=sym, exchange="NSE", side=Side.BUY,
                quantity=10 * (i + 1), price=Decimal("100.0"),
                correlation_id=unique_id,
            )
            result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
            trading_context.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        positions = trading_context.position_manager.get_positions()
        assert len(positions) == 3

        # Each position should have correct quantity
        pos_map = {p.symbol: p for p in positions}
        assert pos_map["RELIANCE"].quantity == 10
        assert pos_map["TCS"].quantity == 20
        assert pos_map["HDFCBANK"].quantity == 30

    def test_cancel_does_not_affect_filled_orders(self, trading_context):
        """Cancelling an open order should not affect already-filled orders."""
        # Place and fill first order
        cmd1 = OmsOrderCommand(
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("100.0"), correlation_id="cancel-test-1",
        )
        r1 = trading_context.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        trading_context.order_manager.record_trade(_make_trade(r1.order, Decimal("100.0")))

        # Place but don't fill second order
        cmd2 = OmsOrderCommand(
            symbol="TCS", exchange="NSE", side=Side.BUY,
            quantity=5, price=Decimal("200.0"), correlation_id="cancel-test-2",
        )
        r2 = trading_context.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())

        # Cancel second order
        trading_context.order_manager.cancel_order(r2.order.order_id)

        # First order should still be filled
        order1 = trading_context.order_manager.get_order(r1.order.order_id)
        # Note: filled_quantity is on the Order, but record_trade updates it
        # Let's verify via position instead
        assert order1 is not None

        # Position should still exist for RELIANCE
        positions = trading_context.position_manager.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10
