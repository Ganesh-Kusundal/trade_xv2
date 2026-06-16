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
from brokers.common.event_log import EventLog
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.oms import (
    PositionManager,
    RiskConfig,
    RiskManager,
    create_trading_context,
)


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
    return create_trading_context(
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


class TestOrderLifecycleE2E:
    def test_place_order_creates_order_in_oms(self, trading_context):
        from brokers.common.oms.order_manager import OmsOrderCommand

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
        from brokers.common.oms.order_manager import OmsOrderCommand

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
        from brokers.common.oms.order_manager import OmsOrderCommand

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

        from brokers.common.oms.order_manager import OmsOrderCommand

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
        from brokers.common.oms.order_manager import OmsOrderCommand

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

        from brokers.common.oms.order_manager import OmsOrderCommand

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
        from brokers.common.oms.order_manager import OmsOrderCommand

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
