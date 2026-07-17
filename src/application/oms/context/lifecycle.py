"""Lifecycle / shutdown methods for TradingContext.

Extracted from context.py to reduce god-object size. These methods handle
graceful shutdown, ManagedService protocol, signal handling, and order
cancellation.
"""

from __future__ import annotations

import logging
import threading
from typing import Any  # Only for signal handler frame type

from application.oms.context._types import CancellationResult
from application.oms.protocols import IBrokerGateway
from infrastructure.lifecycle.lifecycle import ManagedService

logger = logging.getLogger(__name__)


class TradingContextLifecycleMixin(ManagedService):
    """Mixin providing lifecycle / shutdown methods for TradingContext.

    Inherits ManagedService so TradingContext satisfies the protocol
    without the main __init__.py needing to list it as a base class.
    """

    # ManagedService protocol attributes
    name: str = "oms.trading_context"
    _shutdown_gateway: IBrokerGateway | None = None  # Injectable gateway for testing

    async def shutdown(
        self,
        cancel_orders: bool = True,
        gateway: IBrokerGateway | None = None,
    ) -> dict:
        """Graceful shutdown sequence.

        Sequence:
            1. Halt new order placement (set kill_switch)
            2. Cancel all open orders at broker
            3. Flush event log to disk
            4. Emit SYSTEM_SHUTDOWN event

        Args:
            cancel_orders: If True, cancel all open orders at broker.
            gateway: MarketDataGateway for order cancellation. If None,
                     orders are cancelled locally only.

        Returns:
            dict with shutdown results:
                - orders_cancelled: count of successfully cancelled orders
                - orders_failed: count of failed cancellations
                - event_log_flushed: bool
                - connections_closed: int
        """
        with self._shutdown_lock:
            if self._shutdown_in_progress:
                logger.debug("TradingContext.shutdown: already in progress, skipping")
                return {
                    "orders_cancelled": 0,
                    "orders_failed": 0,
                    "event_log_flushed": False,
                    "connections_closed": 0,
                }
            self._shutdown_in_progress = True
        return self._execute_shutdown_sequence(cancel_orders, gateway)

    def _execute_shutdown_sequence(
        self,
        cancel_orders: bool = True,
        gateway: IBrokerGateway | None = None,
    ) -> dict:
        """Shared shutdown steps — delegates to :class:`ShutdownCoordinator`."""
        effective_gateway = gateway or self._shutdown_gateway
        return self._shutdown_coordinator.execute(
            cancel_orders=cancel_orders,
            gateway=effective_gateway,
        )

    def cancel_all_open_orders(
        self,
        gateway: IBrokerGateway | None = None,
    ) -> CancellationResult:
        """Cancel all open orders, optionally via a broker gateway.

        For each OPEN order in the OMS:
            1. If gateway is provided, call gateway.cancel_order()
            2. Update local order status to CANCELLED
            3. Collect success/failure

        Args:
            gateway: MarketDataGateway with cancel_order() method.
        """
        cancelled, failed, failed_ids = self._shutdown_coordinator.cancel_all(
            gateway=gateway,
        )
        return CancellationResult(
            orders_cancelled=cancelled,
            orders_failed=failed,
            failed_order_ids=failed_ids,
        )

    # ── ManagedService protocol implementation ──────────────────────────

    def start(self) -> None:
        """Start the trading context. Idempotent.

        Currently a no-op — the context is fully initialized in
        __init__. This method exists to satisfy the ManagedService
        protocol.
        """
        logger.debug("TradingContext.start: no-op (already initialized)")

    def stop(self, timeout_seconds: float = 30.0) -> None:
        """Stop the trading context. Delegates to shutdown().

        This method satisfies the ManagedService protocol so
        TradingContext can be registered with a LifecycleManager
        for deterministic shutdown.
        """
        logger.info("TradingContext.stop: initiating graceful shutdown")
        try:
            try:
                from application.ports import run_coro_sync

                run_coro_sync(
                    self.shutdown(cancel_orders=True, gateway=self._shutdown_gateway)
                )
            except RuntimeError:
                self._sync_shutdown()
        except Exception as exc:
            logger.exception(
                "TradingContext.stop: shutdown failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    def _sync_shutdown(self) -> dict:
        """Synchronous shutdown path when async is unavailable."""
        with self._shutdown_lock:
            if self._shutdown_in_progress:
                logger.debug("TradingContext._sync_shutdown: already in progress, skipping")
                return {
                    "orders_cancelled": 0,
                    "orders_failed": 0,
                    "event_log_flushed": False,
                    "connections_closed": 0,
                }
            self._shutdown_in_progress = True
        return self._execute_shutdown_sequence(
            cancel_orders=True,
            gateway=self._shutdown_gateway,
        )

    # ── Signal handlers ─────────────────────────────────────────────────

    def register_signal_handlers(self) -> None:
        """Register SIGTERM/SIGINT handlers for graceful shutdown.

        On receiving a signal, the handler calls _sync_shutdown() and
        then exits cleanly. This is Docker/K8s friendly — the
        process terminates within the grace period.

        Must be called from the main thread.
        """
        import signal

        original_handlers = {}

        def _signal_handler(signum: int, frame: Any) -> None:
            sig_name = signal.Signals(signum).name
            logger.info(
                "TradingContext: received %s, initiating graceful shutdown",
                sig_name,
            )
            self._sync_shutdown()
            # Restore original handler and re-raise for default behavior
            if signum in original_handlers:
                signal.signal(signum, original_handlers[signum])

        original_handlers[signal.SIGTERM] = signal.signal(signal.SIGTERM, _signal_handler)
        original_handlers[signal.SIGINT] = signal.signal(signal.SIGINT, _signal_handler)
        logger.info("TradingContext: signal handlers registered for SIGTERM, SIGINT")
