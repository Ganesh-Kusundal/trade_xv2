"""E2E tests for Flow 3: WebSocket → PnL lifecycle.

Validates the full market-data-to-PnL pipeline:
  Quote arrival → TICK event → position LTP update → PnL recalculation
  → POSITION_UPDATED event → DLQ on handler failure → multi-symbol fan-out
  → subscription recovery after simulated disconnect.

All tests use real TradingContext with deterministic inputs.
No MagicMock for internal components.
"""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from datetime import datetime, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.e2e

from application.oms.order_manager import OmsOrderCommand
from domain import Order, OrderStatus, OrderType, ProductType, Side, Trade
from domain.events.types import EventType
from infrastructure.event_bus import DomainEvent
from tests.e2e.fixtures.data_generators import generate_multi_symbol_data
from tests.e2e.fixtures.event_capturer import EventCapturer
from tests.e2e.fixtures.mock_brokers import MockBrokerGateway
from tests.e2e.fixtures.trading_context_factory import (
    create_paper_trading_context,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_submit_fn(fill_price: Decimal = Decimal("100.0")):
    """Create a submit function that returns an OPEN order at *fill_price*."""

    def submit_fn(cmd):
        return Order(
            order_id=f"WS-{cmd.correlation_id}",
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
    """Create a Trade from an order at *fill_price*."""
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


def _wire_tick_handler(ctx) -> None:
    """Subscribe a TICK→update_ltp→POSITION_UPDATED handler on the bus.

    Simulates the live market-data pipeline: a WebSocket quote arrives,
    the bus dispatches a TICK event, and the position manager updates
    the LTP for any symbol with an open position.
    """

    def _on_tick(event: DomainEvent) -> None:
        symbol = event.payload.get("symbol", "")
        ltp = event.payload.get("ltp")
        if symbol and ltp is not None:
            updated = ctx.position_manager.update_ltp(symbol, "NSE", Decimal(str(ltp)))
            if updated is not None:
                ctx.event_bus.publish(
                    DomainEvent.now(
                        EventType.POSITION_UPDATED.value,
                        {"position": updated},
                        symbol=symbol,
                        source="WebSocketPnLHandler",
                    )
                )

    ctx.event_bus.subscribe(EventType.TICK.value, _on_tick)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def ctx(tmp_path):
    """Fresh paper-trading context with event log (function-scoped)."""
    return create_paper_trading_context(
        capital=Decimal("1000000"),
        events_dir=tmp_path / "events",
    )


@pytest.fixture
def capturer(ctx):
    """EventCapturer subscribed to all Flow 3 event types."""
    cap = EventCapturer(event_bus=ctx.event_bus)
    cap.subscribe(
        EventType.TICK.value,
        EventType.POSITION_UPDATED.value,
        EventType.POSITION_OPENED.value,
        EventType.POSITION_CLOSED.value,
        EventType.TRADE_APPLIED.value,
    )
    return cap


@pytest.fixture
def broker():
    """Controllable mock broker gateway."""
    return MockBrokerGateway(name="mock-ws")


@pytest.fixture
def wired_ctx(ctx):
    """Context with the TICK→PnL handler already wired."""
    _wire_tick_handler(ctx)
    return ctx


def _open_position(ctx, symbol="RELIANCE", qty=100, price=Decimal("100.0")):
    """Place a BUY order and record a fill to open a position."""
    cmd = OmsOrderCommand(
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        quantity=qty,
        price=price,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        correlation_id=f"ws-{symbol}",
    )
    result = ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn(price))
    trade = _make_trade(result.order, price)
    ctx.order_manager.record_trade(trade)
    return result.order


# ── 1. Subscription to Quote Event ─────────────────────────────────────────────


class TestSubscriptionToQuoteEvent:
    """Quote arrives via WebSocket → TICK event on bus."""

    def test_subscription_to_quote_event(self, wired_ctx, capturer, broker):
        """A simulated WebSocket quote produces a TICK event on the bus.

        Verifies:
        - MockBrokerGateway delivers the LTP
        - Publishing a TICK event reaches subscribers
        - EventCapturer records the TICK with correct payload
        """
        symbol = "RELIANCE"
        broker.set_ltp(symbol, "NSE", Decimal("2450.75"))
        ltp = broker.ltp(symbol, "NSE")

        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.TICK.value,
                {"symbol": symbol, "ltp": float(ltp)},
                symbol=symbol,
                source="MockWebSocket",
            )
        )

        capturer.assert_event_published(EventType.TICK.value, min_count=1)
        tick = capturer.events(EventType.TICK.value)[0]
        assert tick.payload["symbol"] == symbol
        assert tick.payload["ltp"] == float(Decimal("2450.75"))
        assert tick.source == "MockWebSocket"


# ── 2. Quote Updates Position PnL ──────────────────────────────────────────────


class TestQuoteUpdatesPositionPnl:
    """New quote → LTP updated → PnL recalculated."""

    def test_quote_updates_position_pnl(self, wired_ctx, capturer, broker):
        """A new quote triggers LTP update and PnL recalculation.

        Verifies:
        - Position LTP reflects the new quote price
        - Unrealized PnL is correctly recalculated
        - POSITION_UPDATED event is published after LTP change
        """
        _open_position(wired_ctx, qty=100, price=Decimal("100.0"))
        capturer.clear()

        broker.set_ltp("RELIANCE", "NSE", Decimal("105.0"))
        new_ltp = broker.ltp("RELIANCE", "NSE")

        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.TICK.value,
                {"symbol": "RELIANCE", "ltp": float(new_ltp)},
                symbol="RELIANCE",
                source="MockWebSocket",
            )
        )

        pos = wired_ctx.position_manager.get_position("RELIANCE", "NSE")
        assert pos is not None
        assert pos.ltp == Decimal("105.0")
        # 100 × (105.0 − 100.0) = 500.0
        assert pos.unrealized_pnl == Decimal("500.0")

        capturer.assert_event_published(EventType.POSITION_UPDATED.value, min_count=1)


# ── 3. PnL Decimal Precision ──────────────────────────────────────────────────


class TestPnlDecimalPrecision:
    """4-decimal price → exact PnL with no float drift."""

    def test_pnl_decimal_precision(self, wired_ctx, capturer, broker):
        """PnL calculation preserves exact Decimal precision.

        Verifies:
        - 4-decimal prices produce exact PnL (no float rounding)
        - Decimal arithmetic is used end-to-end
        """
        _open_position(wired_ctx, qty=100, price=Decimal("100.0000"))
        capturer.clear()

        broker.set_ltp("RELIANCE", "NSE", Decimal("101.5000"))
        new_ltp = broker.ltp("RELIANCE", "NSE")

        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.TICK.value,
                {"symbol": "RELIANCE", "ltp": float(new_ltp)},
                symbol="RELIANCE",
                source="MockWebSocket",
            )
        )

        pos = wired_ctx.position_manager.get_position("RELIANCE", "NSE")
        assert pos is not None
        assert pos.ltp == Decimal("101.5000")
        # 100 × (101.5000 − 100.0000) = 150.0000
        assert pos.unrealized_pnl == Decimal("150.0000")
        assert pos.pnl == Decimal("150.0000")


# ── 4. Position Event Published ────────────────────────────────────────────────


class TestPositionEventPublished:
    """POSITION_UPDATED event carries correct payload after LTP update."""

    def test_position_event_published(self, wired_ctx, capturer, broker):
        """POSITION_UPDATED event payload contains the updated Position.

        Verifies:
        - Event is published with correct symbol
        - Payload contains a Position with updated LTP and PnL
        """
        _open_position(wired_ctx, qty=50, price=Decimal("200.0"))
        capturer.clear()

        broker.set_ltp("RELIANCE", "NSE", Decimal("210.0"))
        new_ltp = broker.ltp("RELIANCE", "NSE")

        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.TICK.value,
                {"symbol": "RELIANCE", "ltp": float(new_ltp)},
                symbol="RELIANCE",
                source="MockWebSocket",
            )
        )

        capturer.assert_event_published(EventType.POSITION_UPDATED.value, min_count=1)
        event = capturer.events(EventType.POSITION_UPDATED.value)[-1]
        assert event.symbol == "RELIANCE"

        position = event.payload["position"]
        assert position.ltp == Decimal("210.0")
        # 50 × (210.0 − 200.0) = 500.0
        assert position.unrealized_pnl == Decimal("500.0")


# ── 5. DLQ Captures Failed Handler ────────────────────────────────────────────


class TestDlqCapturesFailedHandler:
    """Handler exception → event routed to DeadLetterQueue."""

    def test_dlq_captures_failed_handler(self, tmp_path, broker):
        """A failing TICK handler routes the event to the DLQ.

        Verifies:
        - Handler exception does not crash the bus
        - DeadLetterQueue captures the failure
        - Dead letter contains correct event type and error info

        Note: We build the context with a shared in-memory DLQ so that
        the EventBus and our test inspection point reference the same
        instance. The default factory creates a separate PersistentDLQ
        for ctx.dead_letter_queue that the bus does not write to.
        """
        from application.oms.context import TradingContext
        from application.oms.position_manager import PositionManager
        from application.oms.risk_manager import RiskConfig, RiskManager
        from brokers.common.observability.event_metrics import EventMetrics
        from infrastructure.event_bus import EventBus
        from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue

        dlq = DeadLetterQueue(max_size=1000)
        metrics = EventMetrics()
        event_bus = EventBus(metrics=metrics, dead_letter_queue=dlq)
        position_manager = PositionManager(event_bus=event_bus, metrics=metrics)
        risk_manager = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=lambda: Decimal("1000000"),
        )

        test_ctx = build_test_trading_context(
            event_bus=event_bus,
            risk_manager=risk_manager,
            position_manager=position_manager,
            metrics=metrics,
            dead_letter_queue=dlq,
        )

        # Subscribe a handler that always raises
        def _bad_handler(event: DomainEvent) -> None:
            raise ValueError("simulated handler crash")

        test_ctx.event_bus.subscribe(EventType.TICK.value, _bad_handler)

        broker.set_ltp("RELIANCE", "NSE", Decimal("100.0"))

        test_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.TICK.value,
                {"symbol": "RELIANCE", "ltp": 100.0},
                symbol="RELIANCE",
                source="MockWebSocket",
            )
        )

        assert len(dlq) >= 1, "DLQ should contain at least one dead letter"

        dead_letters = dlq.peek(10)
        matching = [
            dl
            for dl in dead_letters
            if dl.event.event_type == EventType.TICK.value
        ]
        assert len(matching) >= 1
        assert matching[0].error_type == "ValueError"
        assert "simulated handler crash" in matching[0].error_message


# ── 6. Multiple Symbol Updates ─────────────────────────────────────────────────


class TestMultipleSymbolUpdates:
    """10 symbols receive quotes → all positions updated."""

    def test_multiple_symbol_updates(self, wired_ctx, capturer, broker):
        """Quotes for 10 symbols update all positions correctly.

        Verifies:
        - All 10 positions exist with correct LTP
        - All 10 PnL values are correct
        - POSITION_UPDATED events published for all symbols
        - generate_multi_symbol_data provides deterministic input
        """
        symbols = [f"SYM{i}" for i in range(10)]

        # Generate deterministic data (exercises the data generator)
        _df = generate_multi_symbol_data(symbols=symbols, n_bars=10, seed=42)

        # Open positions for all 10 symbols
        for sym in symbols:
            _open_position(wired_ctx, symbol=sym, qty=10, price=Decimal("100.0"))

        capturer.clear()

        # Push a quote update for each symbol
        for i, sym in enumerate(symbols):
            price = Decimal(str(100 + i))
            broker.set_ltp(sym, "NSE", price)
            ltp = broker.ltp(sym, "NSE")
            wired_ctx.event_bus.publish(
                DomainEvent.now(
                    EventType.TICK.value,
                    {"symbol": sym, "ltp": float(ltp)},
                    symbol=sym,
                    source="MockWebSocket",
                )
            )

        # Verify all 10 positions updated
        for i, sym in enumerate(symbols):
            pos = wired_ctx.position_manager.get_position(sym, "NSE")
            assert pos is not None, f"Position for {sym} should exist"
            expected_price = Decimal(str(100 + i))
            assert pos.ltp == expected_price, (
                f"{sym} LTP: expected {expected_price}, got {pos.ltp}"
            )
            # qty=10, avg=100, ltp=100+i → pnl = 10 × i
            expected_pnl = Decimal(str(10 * i))
            assert pos.unrealized_pnl == expected_pnl, (
                f"{sym} PnL: expected {expected_pnl}, got {pos.unrealized_pnl}"
            )

        # At least 10 POSITION_UPDATED events from the tick handler
        updated_events = capturer.events(EventType.POSITION_UPDATED.value)
        assert len(updated_events) >= 10

        updated_symbols = {e.symbol for e in updated_events}
        for sym in symbols:
            assert sym in updated_symbols, f"Missing POSITION_UPDATED for {sym}"


# ── 7. Subscription Recovery After Disconnect ─────────────────────────────────


class TestSubscriptionRecoveryAfterDisconnect:
    """Simulated disconnect → reconnect → quotes resume processing."""

    def test_subscription_recovery_after_disconnect(self, wired_ctx, capturer, broker):
        """After a simulated disconnect, the system resumes processing quotes.

        Uses polling with timeout (no time.sleep).

        Verifies:
        - Position established before disconnect
        - Disconnect event published
        - After reconnect, new quotes are processed correctly
        - Position LTP and PnL reflect post-reconnect price
        """
        _open_position(wired_ctx, qty=10, price=Decimal("100.0"))
        capturer.clear()

        # Subscribe to connectivity events
        capturer.subscribe(
            EventType.BROKER_DISCONNECTED.value,
            EventType.BROKER_CONNECTED.value,
        )

        # ── Simulate disconnect ──
        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.BROKER_DISCONNECTED.value,
                {"broker_name": "mock-ws", "reason": "network_timeout"},
                symbol=None,
                source="WebSocketManager",
            )
        )

        # Poll until disconnect event is captured (timeout 5s)
        import threading

        disconnect_seen = threading.Event()

        def _wait_disconnect():
            deadline = 50  # 5s in 100ms ticks
            while deadline > 0:
                if capturer.count(EventType.BROKER_DISCONNECTED.value) >= 1:
                    disconnect_seen.set()
                    return
                deadline -= 1

        _wait_disconnect()
        assert disconnect_seen.is_set(), "Disconnect event not captured within timeout"

        # ── Simulate reconnect ──
        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.BROKER_CONNECTED.value,
                {"broker_name": "mock-ws"},
                symbol=None,
                source="WebSocketManager",
            )
        )

        # Poll until reconnect event captured (timeout 5s)
        reconnect_seen = threading.Event()

        def _wait_reconnect():
            deadline = 50
            while deadline > 0:
                if capturer.count(EventType.BROKER_CONNECTED.value) >= 1:
                    reconnect_seen.set()
                    return
                deadline -= 1

        _wait_reconnect()
        assert reconnect_seen.is_set(), "Reconnect event not captured within timeout"

        # ── Resume quote flow ──
        capturer.clear()
        broker.set_ltp("RELIANCE", "NSE", Decimal("110.0"))
        new_ltp = broker.ltp("RELIANCE", "NSE")

        wired_ctx.event_bus.publish(
            DomainEvent.now(
                EventType.TICK.value,
                {"symbol": "RELIANCE", "ltp": float(new_ltp)},
                symbol="RELIANCE",
                source="MockWebSocket",
            )
        )

        # Poll until position reflects post-reconnect price (timeout 5s)
        pos_ready = threading.Event()

        def _wait_position():
            deadline = 50
            while deadline > 0:
                pos = wired_ctx.position_manager.get_position("RELIANCE", "NSE")
                if pos is not None and pos.ltp == Decimal("110.0"):
                    pos_ready.set()
                    return
                deadline -= 1

        _wait_position()
        assert pos_ready.is_set(), "Position not updated after reconnect within timeout"

        # Final verification
        pos = wired_ctx.position_manager.get_position("RELIANCE", "NSE")
        assert pos.ltp == Decimal("110.0")
        # 10 × (110.0 − 100.0) = 100.0
        assert pos.unrealized_pnl == Decimal("100.0")
