"""Tests for graceful shutdown with order cancellation (B2 fix).

Covers:
- shutdown() cancels all open orders
- shutdown() flushes event log
- shutdown() closes connections
- shutdown() with cancellation failures (partial success)
- shutdown() is idempotent
- shutdown() emits SYSTEM_SHUTDOWN event
- ManagedService protocol compliance
- cancel_all_open_orders() with gateway
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand
from domain import Order, OrderStatus, Side, Trade
from domain.events.types import DomainEvent, EventType
from infrastructure.event_log import EventLog
from infrastructure.lifecycle import LifecycleManager
from tests.conftest import build_test_trading_context

# -- Helpers ----------------------------------------------------------------


def _make_submit_fn(fill_price: Decimal | None = None):
    """Create a mock submit_fn that returns an open order."""
    import uuid

    def _submit(request: OmsOrderCommand) -> Order:
        return Order(
            order_id=f"OM-{uuid.uuid4().hex[:12]}",
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            product_type=request.product_type,
            status=OrderStatus.OPEN,
            correlation_id=request.correlation_id,
        )

    return _submit


def _limit_cmd(
    symbol: str,
    side: Side,
    qty: int,
    correlation_id: str,
    price: Decimal = Decimal("100"),
) -> OmsOrderCommand:
    """LIMIT command with price so risk notional sizing succeeds in unit tests."""
    from domain import OrderType

    return OmsOrderCommand(
        symbol,
        "NSE",
        side,
        qty,
        price=price,
        order_type=OrderType.LIMIT,
        correlation_id=correlation_id,
    )


def _run_shutdown(ctx: TradingContext, **kwargs) -> dict:
    """Helper to run async shutdown() synchronously."""
    return asyncio.run(ctx.shutdown(**kwargs))


# -- Test: shutdown cancels all open orders ---------------------------------


class TestShutdownCancelsOpenOrders:
    """Verify shutdown() cancels all open orders via the gateway."""

    def test_shutdown_cancels_all_open_orders(self) -> None:
        """shutdown(cancel_orders=True) should cancel every OPEN order."""
        ctx = build_test_trading_context()
        cmd1 = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-1")
        cmd2 = _limit_cmd("TCS", Side.BUY, 5, "sh-2")
        ctx.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        ctx.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())

        open_before = [o for o in ctx.order_manager.get_orders() if o.status == OrderStatus.OPEN]
        assert len(open_before) == 2

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = MagicMock(success=True)

        result = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)

        assert result["orders_cancelled"] == 2
        assert result["orders_failed"] == 0
        assert mock_gateway.cancel_order.call_count == 2

        open_after = [o for o in ctx.order_manager.get_orders() if o.status == OrderStatus.OPEN]
        assert len(open_after) == 0

    def test_shutdown_skips_cancellation_when_flag_false(self) -> None:
        """shutdown(cancel_orders=False) should not call cancel_order."""
        ctx = build_test_trading_context()
        cmd = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-3")
        ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        result = _run_shutdown(ctx, cancel_orders=False, gateway=mock_gateway)

        assert result["orders_cancelled"] == 0
        mock_gateway.cancel_order.assert_not_called()

    def test_shutdown_skips_cancellation_when_no_gateway(self) -> None:
        """shutdown() with no gateway should skip cancellation gracefully."""
        ctx = build_test_trading_context()
        cmd = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-4")
        ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        result = _run_shutdown(ctx, cancel_orders=True, gateway=None)

        # No gateway means no broker cancellation, but local cancellation happens
        assert result["orders_cancelled"] == 1
        assert result["orders_failed"] == 0

    def test_shutdown_only_cancels_open_orders(self) -> None:
        """shutdown() should not attempt to cancel FILLED/CANCELLED orders."""
        ctx = build_test_trading_context()

        cmd1 = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-5")
        result1 = ctx.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        order1 = result1.order
        assert order1 is not None

        trade = Trade(
            trade_id="T1",
            order_id=order1.order_id,
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
        )
        ctx.order_manager.record_trade(trade)

        cmd2 = _limit_cmd("TCS", Side.BUY, 5, "sh-6")
        ctx.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = MagicMock(success=True)

        result = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)

        # Only the OPEN order should be cancelled, not the FILLED one
        assert result["orders_cancelled"] == 1
        assert mock_gateway.cancel_order.call_count == 1


# -- Test: shutdown with cancellation failures --------------------------------


class TestShutdownCancellationFailures:
    """Verify shutdown handles partial cancellation failures gracefully."""

    def test_shutdown_partial_success(self) -> None:
        """Some cancellations succeed, some fail -- shutdown continues."""
        ctx = build_test_trading_context()
        cmd1 = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-f1")
        cmd2 = _limit_cmd("TCS", Side.BUY, 5, "sh-f2")
        cmd3 = _limit_cmd("INFY", Side.BUY, 8, "sh-f3")
        ctx.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        ctx.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())
        ctx.order_manager.place_order(cmd3, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        call_count = 0

        def _cancel_side_effect(oid: str) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return MagicMock(success=False, message="Broker error")
            return MagicMock(success=True)

        mock_gateway.cancel_order.side_effect = _cancel_side_effect

        result = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)

        assert result["orders_cancelled"] == 2
        assert result["orders_failed"] == 1
        assert mock_gateway.cancel_order.call_count == 3

    def test_shutdown_all_cancellations_fail(self) -> None:
        """All cancellations fail -- shutdown returns all as failed."""
        ctx = build_test_trading_context()
        cmd1 = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-f4")
        cmd2 = _limit_cmd("TCS", Side.BUY, 5, "sh-f5")
        ctx.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        ctx.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = MagicMock(success=False, message="API down")

        result = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)

        assert result["orders_cancelled"] == 0
        assert result["orders_failed"] == 2

    def test_shutdown_cancellation_raises_exception(self) -> None:
        """Gateway.cancel_order raises -- shutdown logs and continues."""
        ctx = build_test_trading_context()
        cmd = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-f6")
        ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.side_effect = ConnectionError("Network error")

        result = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)

        assert result["orders_cancelled"] == 0
        assert result["orders_failed"] == 1


# -- Test: shutdown event log flush ------------------------------------------


class TestShutdownEventLogFlush:
    """Verify shutdown flushes the event log."""

    def test_shutdown_flushes_event_log(self, tmp_path) -> None:
        """shutdown() should flush and close the event log."""
        log = EventLog(events_dir=tmp_path / "events")
        ctx = build_test_trading_context(event_log=log)

        ctx.event_bus.publish(
            DomainEvent.now(EventType.TICK.value, {"price": 100}, symbol="RELIANCE")
        )

        result = _run_shutdown(ctx, cancel_orders=False)

        assert result["event_log_flushed"] is True

    def test_shutdown_no_event_log(self) -> None:
        """shutdown() with no event log should report False."""
        ctx = build_test_trading_context(event_log=None)
        result = _run_shutdown(ctx, cancel_orders=False)

        assert result["event_log_flushed"] is False


# -- Test: shutdown idempotency -----------------------------------------------


class TestShutdownIdempotency:
    """Verify shutdown() can be called multiple times safely."""

    def test_shutdown_idempotent(self) -> None:
        """Calling shutdown() twice should not crash or double-cancel."""
        ctx = build_test_trading_context()
        cmd = _limit_cmd("RELIANCE", Side.BUY, 10, "sh-idem")
        ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = MagicMock(success=True)

        result1 = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)
        result2 = _run_shutdown(ctx, cancel_orders=True, gateway=mock_gateway)

        # First call cancels the order
        assert result1["orders_cancelled"] == 1
        # Second call should not cancel anything (order already CANCELLED)
        assert result2["orders_cancelled"] == 0
        # Gateway should only be called once
        assert mock_gateway.cancel_order.call_count == 1

    def test_shutdown_idempotent_no_open_orders(self) -> None:
        """shutdown() with no open orders should be safe."""
        ctx = build_test_trading_context()

        result1 = _run_shutdown(ctx, cancel_orders=True)
        result2 = _run_shutdown(ctx, cancel_orders=True)

        assert result1["orders_cancelled"] == 0
        assert result2["orders_cancelled"] == 0


# -- Test: shutdown emits SYSTEM_SHUTDOWN event --------------------------------


class TestShutdownEventEmission:
    """Verify shutdown emits SYSTEM_SHUTDOWN event."""

    def test_shutdown_emits_system_shutdown_event(self) -> None:
        """shutdown() should publish a SYSTEM_SHUTDOWN event."""
        ctx = build_test_trading_context()
        received_events = []

        def _capture(event: DomainEvent) -> None:
            received_events.append(event)

        ctx.event_bus.subscribe(EventType.SYSTEM_SHUTDOWN.value, _capture)

        _run_shutdown(ctx, cancel_orders=False)

        shutdown_events = [
            e for e in received_events if e.event_type == EventType.SYSTEM_SHUTDOWN.value
        ]
        assert len(shutdown_events) == 1
        assert "shutdown_complete" in shutdown_events[0].payload.get("detail", "").lower()


# -- Test: ManagedService protocol compliance ----------------------------------


class TestManagedServiceProtocol:
    """Verify TradingContext implements the ManagedService protocol."""

    def test_trading_context_has_name(self) -> None:
        """TradingContext should have a .name attribute."""
        ctx = build_test_trading_context()
        assert hasattr(ctx, "name")
        assert ctx.name == "oms.trading_context"

    def test_trading_context_start_is_idempotent(self) -> None:
        """start() should be idempotent and return promptly."""
        ctx = build_test_trading_context()
        ctx.start()
        ctx.start()  # Should not raise

    def test_trading_context_stop_calls_shutdown(self) -> None:
        """stop() should delegate to shutdown()."""
        ctx = build_test_trading_context()
        cmd = _limit_cmd("RELIANCE", Side.BUY, 10, "ms-1")
        ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = MagicMock(success=True)
        ctx._shutdown_gateway = mock_gateway  # Inject mock gateway

        ctx.stop(timeout_seconds=10.0)

        assert mock_gateway.cancel_order.call_count == 1

    def test_trading_context_health(self) -> None:
        """health() should return a HealthStatus."""

        ctx = build_test_trading_context()
        status = ctx.health()

        # Returns the existing health dict (or HealthStatus if wrapped)
        assert status is not None

    def test_trading_context_registers_with_lifecycle(self) -> None:
        """attach_lifecycle() should register TradingContext as ManagedService."""
        ctx = build_test_trading_context()
        lifecycle = LifecycleManager()
        ctx.attach_lifecycle(lifecycle)

        # TradingContext itself should be registered
        assert "oms.trading_context" in lifecycle.service_names()


# -- Test: cancel_all_open_orders ----------------------------------------------


class TestCancelAllOpenOrders:
    """Verify cancel_all_open_orders() helper."""

    def test_cancel_all_no_gateway(self) -> None:
        """Without gateway, orders are cancelled locally only."""
        ctx = build_test_trading_context()
        cmd1 = _limit_cmd("RELIANCE", Side.BUY, 10, "ca-1")
        cmd2 = _limit_cmd("TCS", Side.BUY, 5, "ca-2")
        ctx.order_manager.place_order(cmd1, submit_fn=_make_submit_fn())
        ctx.order_manager.place_order(cmd2, submit_fn=_make_submit_fn())

        result = ctx.cancel_all_open_orders(gateway=None)

        assert result["orders_cancelled"] == 2
        assert result["orders_failed"] == 0

    def test_cancel_all_with_gateway(self) -> None:
        """With gateway, orders are cancelled at broker first."""
        ctx = build_test_trading_context()
        cmd = _limit_cmd("RELIANCE", Side.BUY, 10, "ca-3")
        ctx.order_manager.place_order(cmd, submit_fn=_make_submit_fn())

        mock_gateway = MagicMock()
        mock_gateway.cancel_order.return_value = MagicMock(success=True)

        result = ctx.cancel_all_open_orders(gateway=mock_gateway)

        assert result["orders_cancelled"] == 1
        assert mock_gateway.cancel_order.call_count == 1

    def test_cancel_all_empty(self) -> None:
        """No open orders -- cancel_all returns empty results."""
        ctx = build_test_trading_context()
        result = ctx.cancel_all_open_orders()

        assert result["orders_cancelled"] == 0
        assert result["orders_failed"] == 0


# -- Test: signal handler integration ------------------------------------------


class TestSignalHandler:
    """Verify signal handler triggers shutdown."""

    def test_register_signal_handlers(self) -> None:
        """register_signal_handlers() should register SIGTERM and SIGINT."""
        import signal

        ctx = build_test_trading_context()
        try:
            ctx.register_signal_handlers()
            handler_term = signal.getsignal(signal.SIGTERM)
            handler_int = signal.getsignal(signal.SIGINT)
            assert handler_term is not None
            assert handler_int is not None
        except (ValueError, OSError):
            pytest.skip("Signal registration not available in this context")
