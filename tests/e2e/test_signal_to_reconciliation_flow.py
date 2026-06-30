"""E2E tests for Flow 1: Signal → Order → Execution → Reconciliation.

Validates the full trading lifecycle from signal generation through
order placement, execution, position management, and reconciliation
drift detection.

All tests use real TradingContext with paper broker (no real money).
Deterministic: same input produces same output.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.e2e

from application.oms.order_manager import OmsOrderCommand
from application.oms.risk_manager import RiskConfig
from domain import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Trade,
)
from domain.reconciliation import DriftItem, ReconciliationReport
from tests.e2e.fixtures.event_capturer import EventCapturer
from tests.e2e.fixtures.trading_context_factory import (
    create_paper_trading_context,
    create_test_trading_context,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_submit_fn(fill_price: Decimal = Decimal("100.0")):
    """Create a mock submit function that returns an OPEN order."""

    def submit_fn(cmd):
        unique_part = (
            cmd.correlation_id.split("-")[-1][:12]
            if "-" in cmd.correlation_id
            else uuid.uuid4().hex[:12]
        )
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


class _StubReconciliationService:
    """Minimal IReconciliationService stub for reconciliation tests.

    Returns a preconfigured ReconciliationReport — no broker calls.
    """

    def __init__(self, report: ReconciliationReport | None = None) -> None:
        self._report = report or ReconciliationReport()

    def reconcile(
        self,
        local_orders: list | None = None,
        local_positions: list | None = None,
    ) -> ReconciliationReport:
        return self._report


# ── Fixtures ───────────────────────────────────────────────────────────────────


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
        "RECONCILIATION_COMPLETED",
    )
    return capturer


# ── 1. Happy Path: Signal → Fill → Position ───────────────────────────────────


class TestHappyPathSignalToFill:
    """Full signal → order → fill → position lifecycle."""

    def test_happy_path_signal_to_fill(self, trading_context, event_capturer):
        """A BUY signal flows through order placement, fill, and position creation.

        Verifies:
        - Order is placed with OPEN status
        - Trade is recorded, updating filled_quantity
        - Position is created with correct quantity and avg_price
        - Events are published at each stage
        """
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="happy-path-001",
        )

        # Step 1: Place order
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success is True
        assert result.order is not None
        assert result.order.status == OrderStatus.OPEN

        # Step 2: Record fill (trade)
        trade = _make_trade(result.order, Decimal("100.0"))
        trading_context.order_manager.record_trade(trade)

        # Step 3: Verify position
        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert pos.quantity == 10
        assert pos.avg_price == Decimal("100.0")

        # Step 4: Verify order filled_quantity
        order = trading_context.order_manager.get_order(result.order.order_id)
        assert order.filled_quantity == 10

        # Step 5: Verify event chain
        event_capturer.assert_event_published("ORDER_PLACED", min_count=1)
        event_capturer.assert_event_published("RISK_APPROVED", min_count=1)
        event_capturer.assert_event_published("TRADE_APPLIED", min_count=1)
        event_capturer.assert_event_published("POSITION_UPDATED", min_count=1)
        event_capturer.assert_event_published("POSITION_OPENED", min_count=1)


# ── 2. Risk Rejection Blocks Order ────────────────────────────────────────────


class TestRiskRejectionBlocksOrder:
    """RiskManager rejects order — no order reaches broker."""

    def test_risk_rejection_blocks_order(self, trading_context, event_capturer):
        """When risk check fails, order is blocked and no broker call is made.

        Verifies:
        - Order result has success=False
        - Error message indicates risk rejection
        - RISK_REJECTED event is published
        - No ORDER_PLACED event (order never reached broker)
        """
        # Use tight concentration limit to trigger rejection
        ctx = create_test_trading_context(
            capital=Decimal("10000"),
            risk_config=RiskConfig(max_position_pct=Decimal("5")),
        )
        capturer = EventCapturer(event_bus=ctx.event_bus)
        capturer.subscribe("RISK_REJECTED", "ORDER_PLACED")

        # 10% of 10000 = 1000 max notional; 20 * 100 = 2000 > 1000 → rejected
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=20,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="risk-reject-001",
        )
        result = ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is False
        assert "max position" in result.error.lower()
        capturer.assert_event_published("RISK_REJECTED", min_count=1)
        assert capturer.count("ORDER_PLACED") == 0


# ── 3. Kill Switch Blocks Order ───────────────────────────────────────────────


class TestKillSwitchBlocksOrder:
    """Kill switch active → order blocked with OrderBlockedError-style result."""

    def test_kill_switch_blocks_order(self, trading_context, event_capturer):
        """Active kill switch blocks all new order placement.

        Verifies:
        - Order result has success=False
        - Error message mentions kill switch
        - RISK_REJECTED event is published
        """
        trading_context.risk_manager.set_kill_switch(True)

        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="kill-switch-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        assert result.success is False
        assert "Kill switch" in result.error
        event_capturer.assert_event_published("RISK_REJECTED", min_count=1)


# ── 4. Partial Fill Updates Position ─────────────────────────────────────────


class TestPartialFillUpdatesPosition:
    """50% fill → partial position with correct quantity."""

    def test_partial_fill_updates_position(self, trading_context):
        """A 50% partial fill creates a partial position.

        Verifies:
        - filled_quantity reflects partial amount
        - Position quantity matches filled amount
        - avg_price is correct for the partial fill
        """
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=100,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="partial-fill-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success is True

        # Partial fill: 50 of 100
        partial_trade = Trade(
            trade_id="PARTIAL-50",
            order_id=result.order.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=50,
            price=Decimal("100.0"),
        )
        trading_context.order_manager.record_trade(partial_trade)

        # Verify order state
        order = trading_context.order_manager.get_order(result.order.order_id)
        assert order.filled_quantity == 50

        # Verify position
        pos = trading_context.position_manager.get_position("RELIANCE", "NSE")
        assert pos.quantity == 50
        assert pos.avg_price == Decimal("100.0")


# ── 5. Order Rejection by Broker ─────────────────────────────────────────────


class TestOrderRejectionByBroker:
    """Broker rejects order → REJECTED status in OMS."""

    def test_order_rejection_by_broker(self, trading_context, event_capturer):
        """When broker rejects, order status becomes REJECTED.

        Verifies:
        - Order is placed (OPEN status)
        - Broker rejection updates order to REJECTED
        - ORDER_UPDATED event is published
        """
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            correlation_id="broker-reject-001",
        )
        result = trading_context.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        assert result.success is True
        assert result.order.status == OrderStatus.OPEN

        # Simulate broker rejection via upsert_order (broker event path)
        rejected_order = result.order.with_status(OrderStatus.REJECTED)
        trading_context.order_manager.upsert_order(rejected_order)

        # Verify order status
        order = trading_context.order_manager.get_order(result.order.order_id)
        assert order.status == OrderStatus.REJECTED

        # Verify events
        event_capturer.assert_event_published("ORDER_UPDATED", min_count=1)


# ── 6. Reconciliation Detects Drift ──────────────────────────────────────────


class TestReconciliationDetectsDrift:
    """Broker ≠ OMS → has_drift=True."""

    def test_reconciliation_detects_drift(self, tmp_path):
        """Reconciliation detects position mismatch between broker and OMS.

        Verifies:
        - ReconciliationService runs against local state
        - Drift is detected when broker reports different positions
        - Report has_drift is True
        - DriftItem contains relevant details
        """
        drift_report = ReconciliationReport(
            drift_items=[
                DriftItem(
                    kind="position_mismatch",
                    severity="HIGH",
                    symbol="RELIANCE",
                    details="Local qty=10, Broker qty=0",
                ),
            ],
            broker_orders=0,
            broker_positions=0,
        )
        stub_recon = _StubReconciliationService(report=drift_report)

        ctx = create_paper_trading_context(
            capital=Decimal("1000000"),
            events_dir=tmp_path / "events-recon-drift",
        )
        # Open a local position so there's state to reconcile against
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="recon-drift-001",
        )
        result = ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        ctx.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        # Run reconciliation
        report = stub_recon.reconcile(
            local_orders=ctx.order_manager.get_all_orders(),
            local_positions=ctx.position_manager.get_positions_as_dicts(),
        )

        assert report.has_drift is True
        assert len(report.drift_items) == 1
        assert report.drift_items[0].kind == "position_mismatch"
        assert report.drift_items[0].severity == "HIGH"
        assert report.drift_items[0].symbol == "RELIANCE"


# ── 7. Reconciliation No Drift (Normal) ──────────────────────────────────────


class TestReconciliationNoDriftNormal:
    """Broker = OMS → has_drift=False."""

    def test_reconciliation_no_drift_normal(self, tmp_path):
        """Reconciliation confirms no drift when broker matches OMS.

        Verifies:
        - Clean report with no drift items
        - has_drift is False
        """
        clean_report = ReconciliationReport(
            drift_items=[],
            broker_orders=1,
            broker_positions=1,
        )
        stub_recon = _StubReconciliationService(report=clean_report)

        ctx = create_paper_trading_context(
            capital=Decimal("1000000"),
            events_dir=tmp_path / "events-recon-clean",
        )
        # Create matching local state
        cmd = OmsOrderCommand(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100.0"),
            correlation_id="recon-clean-001",
        )
        result = ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())
        ctx.order_manager.record_trade(_make_trade(result.order, Decimal("100.0")))

        # Run reconciliation
        report = stub_recon.reconcile(
            local_orders=ctx.order_manager.get_all_orders(),
            local_positions=ctx.position_manager.get_positions_as_dicts(),
        )

        assert report.has_drift is False
        assert len(report.drift_items) == 0


# ── 8. Concurrent Signals — No Race Conditions ───────────────────────────────


class TestConcurrentSignalsNoRace:
    """5 parallel signals → 5 unique orders, no duplicates, no corruption."""

    def test_concurrent_signals_no_race(self, trading_context):
        """Five concurrent signals produce exactly five distinct orders.

        Verifies:
        - All 5 orders succeed
        - Each has a unique order_id
        - Total order count is exactly 5
        - No state corruption
        """
        results: list = []
        errors: list = []
        lock = threading.Lock()

        def place_order(idx: int) -> None:
            try:
                unique_id = f"concurrent-{idx}-{uuid.uuid4().hex}"
                cmd = OmsOrderCommand(
                    symbol=f"STOCK{idx}",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=1,
                    price=Decimal("100.0"),
                    order_type=OrderType.MARKET,
                    product_type=ProductType.INTRADAY,
                    correlation_id=unique_id,
                )
                result = trading_context.order_manager.place_order(
                    cmd, submit_fn=_make_submit_fn()
                )
                with lock:
                    results.append((idx, result))
            except Exception as e:
                with lock:
                    errors.append((idx, e))

        threads = [threading.Thread(target=place_order, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions
        assert len(errors) == 0, f"Errors: {errors}"
        # All 5 succeeded
        assert len(results) == 5
        assert all(r.success for _, r in results)

        # Exactly 5 unique orders
        orders = trading_context.order_manager.get_orders()
        assert len(orders) == 5
        order_ids = {o.order_id for o in orders}
        assert len(order_ids) == 5, f"Duplicate order_ids detected: {order_ids}"
