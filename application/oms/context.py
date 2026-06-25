"""Trading context — wires EventBus, OMS, Position and Risk managers."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from application.oms.order_manager import OrderManager
from application.oms.persistence.sqlite_order_store import SqliteOrderStore
from application.oms.position_manager import PositionManager
from application.oms.reconciliation_service import ReconciliationService
from application.oms.risk_manager import RiskConfig, RiskManager
from domain.constants import PHANTOM_CAPITAL_INR, RECONCILIATION_INTERVAL_SECONDS
from infrastructure.event_bus import (
    DeadLetterQueue,
    DomainEvent,
    EventBus,
    EventType,
    ProcessedTradeRepository,
)
from infrastructure.event_bus.persistent_dead_letter_queue import (
    create_default_dead_letter_queue,
)
from infrastructure.event_log import BufferedEventLog, EventLog
from infrastructure.lifecycle import LifecycleManager
from infrastructure.observability.event_metrics import EventMetrics

# P1-Phase 1: Optional import for TradingOrchestrator
# Import only when needed to avoid circular dependency
try:
    from application.trading import TradingOrchestrator

    _HAS_ORCHESTRATOR = True
except ImportError:
    _HAS_ORCHESTRATOR = False
    TradingOrchestrator = None  # type: ignore

logger = logging.getLogger(__name__)


class TradingContext:
    """Container for the central trading services used by gateways and CLI.

    A single context should be shared across an app so that order, position,
    risk and event state remain consistent. The context itself is immutable
    after construction, but the managers it holds are thread-safe and mutate
    their internal state via locks.

    Single-writer invariant
    -----------------------
    Only one live process may own a :class:`TradingContext` writing to a
    given OMS SQLite store and processed-trade ledger path. Running multiple
    instances without external coordination will corrupt idempotency state.

    Optionally accepts a ``reconciliation_service`` and runs periodic
    reconciliation via a background thread.

    Observability wiring
    --------------------
    A production :class:`TradingContext` **must** be constructed with at
    least ``metrics`` and ``dead_letter_queue``. The bus will warn loudly
    if either is missing and a handler raises.

    Parameters
    ----------
    processed_trade_repository:
        Idempotency ledger wired into :class:`OrderManager`. When omitted,
        an in-memory ledger is created (lost on restart).
    metrics:
        :class:`EventMetrics` incremented by the bus and the OMS.
    dead_letter_queue:
        :class:`DeadLetterQueue` that receives failed handler invocations.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        event_log: BufferedEventLog | EventLog | None = None,
        order_manager: OrderManager | None = None,
        position_manager: PositionManager | None = None,
        risk_manager: RiskManager | None = None,
        risk_config: RiskConfig | None = None,
        capital_fn: Callable[[], Decimal] | None = None,
        replay_events: bool = True,
        reconciliation_service: Any = None,
        reconciliation_interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
        processed_trade_repository: ProcessedTradeRepository | None = None,
        metrics: EventMetrics | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        orchestrator: Any | None = None,  # P1-Phase 1: Optional TradingOrchestrator
        durable_order_store: SqliteOrderStore | None = None,
        enable_durable_orders: bool | None = None,
    ) -> None:
        self._event_log = event_log
        self._metrics = metrics or EventMetrics()
        self._dead_letter_queue = dead_letter_queue or create_default_dead_letter_queue()

        # If the caller supplied an event bus, attach observability to it
        # silently; otherwise build a bus that has both observability hooks
        # attached.
        if event_bus is None:
            self._event_bus = EventBus(
                event_log=event_log,
                metrics=self._metrics,
                dead_letter_queue=self._dead_letter_queue,
            )
        else:
            self._event_bus = event_bus

        self._processed_trades = processed_trade_repository or ProcessedTradeRepository()
        # REF-19: enable the self-cleaning thread. It runs as a daemon
        # so it does not block process exit; callers that own a
        # LifecycleManager can stop it deterministically via
        # attach_lifecycle() below.
        self._processed_trades.attach_auto_cleanup()
        _durable = (
            enable_durable_orders
            if enable_durable_orders is not None
            else os.getenv("PYTEST_CURRENT_TEST") is None
        )
        self._position_manager = position_manager or PositionManager(
            event_bus=self._event_bus,
            processed_trade_repository=self._processed_trades,
            metrics=self._metrics,
        )
        self._risk_manager = risk_manager or RiskManager(
            self._position_manager,
            risk_config or RiskConfig(),
            capital_fn or (lambda: PHANTOM_CAPITAL_INR),
        )
        self._order_manager = order_manager or OrderManager(
            event_bus=self._event_bus,
            risk_manager=self._risk_manager,
            processed_trade_repository=self._processed_trades,
            metrics=self._metrics,
            order_store=(
                durable_order_store
                if durable_order_store is not None
                else (SqliteOrderStore() if _durable else None)
            ),
        )

        # Wire managers to the event bus.
        self._event_bus.subscribe(
            EventType.ORDER_UPDATED.value, self._order_manager.on_order_update
        )  # P1-3: Migrated to EventType enum
        # The OMS is the sole gatekeeper for trade idempotency. The
        # position manager subscribes to TRADE_APPLIED (a downstream
        # event the OMS publishes only after a trade has been accepted)
        # rather than to raw TRADE events. This guarantees that
        # duplicate websocket fills cannot double-count positions.
        self._event_bus.subscribe(
            EventType.TRADE.value, self._order_manager.on_trade
        )  # P1-3: Migrated to EventType enum
        self._event_bus.subscribe(
            EventType.TRADE_APPLIED.value, self._position_manager.on_trade_applied
        )  # P1-3: Migrated to EventType enum

        # Reconciliation: an externally-owned ReconciliationService
        # (a ManagedService) is created here so it can be registered
        # with the lifecycle and drained on shutdown. The previous
        # implementation started an anonymous daemon thread inside
        # __init__ and never stopped it.
        self._reconciliation_service: ReconciliationService | None = None
        self._reconciliation_ready = reconciliation_service is None
        if reconciliation_service is not None and reconciliation_interval_seconds > 0:
            self._reconciliation_service = ReconciliationService(
                order_manager=self._order_manager,
                position_manager=self._position_manager,
                reconciliation_service=reconciliation_service,
                interval_seconds=reconciliation_interval_seconds,
                event_bus=self._event_bus,
                on_first_success=self._mark_reconciliation_ready,
            )
            self._order_manager.set_placement_gate(self._reconciliation_placement_gate)

        if replay_events and self._event_log is not None:
            self._replay_log_into_oms()

        # P1-Phase 1: Store orchestrator for lifecycle management
        self._orchestrator: Any = orchestrator

    def attach_lifecycle(self, lifecycle: LifecycleManager) -> None:
        """Register the context's managed services with a lifecycle.

        Callers that own a :class:`LifecycleManager` (the CLI, the TUI,
        the live gateway) MUST call this so the reconciliation service,
        DLQ monitor, DailyPnlResetScheduler, and any future managed
        services participate in deterministic start/stop.
        """
        if self._reconciliation_service is not None:
            lifecycle.register(self._reconciliation_service)
            if os.getenv("TRADEX_SKIP_STARTUP_RECONCILIATION") != "1":
                self._reconciliation_service.run_now()
        # Register deterministic shutdown for the trade-id ledger cleanup thread.
        self._register_processed_trade_cleanup(lifecycle)
        # Register a lightweight DLQ monitor that periodically checks
        # dead-letter queue depth and drains on shutdown so operators
        # don't lose visibility of handler failures.
        self._register_dlq_monitor(lifecycle)
        # Auto-wire DailyPnlResetScheduler — resets _daily_pnl at
        # IST 00:00 so yesterday's loss doesn't block today's orders.
        # Previously only wired by BrokerService; callers that use
        # TradingContext directly (tests, scripts, custom entry points)
        # would silently accumulate PnL across days.
        self._register_daily_pnl_reset(lifecycle)

        # B2: Register TradingContext itself as a ManagedService so
        # it participates in deterministic start/stop via the lifecycle.
        lifecycle.register(self)

        # P1-Phase 1: Register orchestrator for start/stop
        if self._orchestrator is not None:
            lifecycle.register(self._orchestrator)
            logger.info("TradingOrchestrator registered with lifecycle")

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def event_log(self) -> BufferedEventLog | EventLog | None:
        return self._event_log

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk_manager

    @property
    def metrics(self) -> EventMetrics:
        return self._metrics

    @property
    def dead_letter_queue(self) -> DeadLetterQueue:
        return self._dead_letter_queue

    @property
    def processed_trade_repository(self) -> ProcessedTradeRepository:
        return self._processed_trades

    @property
    def orchestrator(self) -> Any | None:  # P1-Phase 1: TradingOrchestrator accessor
        """Access the TradingOrchestrator if configured."""
        return self._orchestrator

    def health(self) -> dict[str, Any]:
        """Snapshot of observability state for the SRE / alerting layer."""
        order_store = getattr(self._order_manager, "_order_store", None)
        return {
            "metrics": self._metrics.snapshot(),
            "dead_letter": self._dead_letter_queue.stats(),
            "trades": self._processed_trades.stats(),
            "event_log_errors": self._event_log.errors if self._event_log else 0,
            "reconciliation_ready": self._reconciliation_ready,
            "oms_writer_lock_held": (
                order_store.writer_lock_held() if order_store is not None else None
            ),
        }

    def _reconciliation_placement_gate(self) -> tuple[bool, str | None]:
        if self._reconciliation_ready:
            return True, None
        return False, "Orders blocked until post-restart reconciliation completes"

    def _mark_reconciliation_ready(self) -> None:
        self._reconciliation_ready = True
        logger.info("Post-restart reconciliation complete — order placement enabled")

    def run_reconciliation(self) -> Any:
        """Run reconciliation immediately (called by timer or manually).

        The actual reconciliation now lives in
        :class:`ReconciliationService`; this is a thin shim kept for
        backward compatibility.
        """
        if self._reconciliation_service is None:
            return None
        return self._reconciliation_service.run_now()

    def stop_reconciliation(self) -> None:
        """Backward-compatible shim that delegates to the service.

        Prefer registering the context with a
        :class:`LifecycleManager` and calling :meth:`LifecycleManager.stop_all`.
        """
        if self._reconciliation_service is None:
            return
        self._reconciliation_service.stop()

    def _register_daily_pnl_reset(self, lifecycle: LifecycleManager) -> None:
        """Auto-wire a DailyPnlResetScheduler so daily PnL is always reset.

        This is the SINGLE registration point for the scheduler.
        BrokerService no longer registers a duplicate (fixed P2-1).
        """
        from application.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler

        scheduler = DailyPnlResetScheduler(risk_manager=self._risk_manager)
        lifecycle.register(scheduler)

    def _register_dlq_monitor(self, lifecycle: LifecycleManager) -> None:
        """Register a lightweight DLQ depth monitor with the lifecycle.

        Periodically logs dead-letter queue depth so operators can alert
        on handler failures. On shutdown (stop), drains the DLQ and logs
        any remaining entries so they are not silently lost.
        """
        from infrastructure.lifecycle import HealthState, ManagedService

        dlq: DeadLetterQueue = self._dead_letter_queue

        class _DlqMonitor(ManagedService):
            name = "oms.dlq_monitor"

            def __init__(self, queue: DeadLetterQueue):
                self._queue = queue
                self._thread: threading.Thread | None = None
                self._stop = threading.Event()
                self._last_depth = 0
                self._total_drained = 0

            def start(self) -> None:
                if self._thread and self._thread.is_alive():
                    return
                self._stop.clear()
                self._thread = threading.Thread(target=self._loop, daemon=True, name="dlq-monitor")
                self._thread.start()

            def stop(self, timeout_seconds: float = 30.0) -> None:
                self._stop.set()
                if self._thread:
                    self._thread.join(timeout=timeout_seconds)
                    self._thread = None
                # Drain remaining DLQ entries on shutdown so they are
                # visible in logs, not silently lost.
                try:
                    drained = self._queue.drain()
                    self._total_drained += len(drained)
                    if drained:
                        logger.warning(
                            "DLQ drain on shutdown: %d entries. First: %s",
                            len(drained),
                            drained[0].to_dict() if drained else "none",
                        )
                except Exception as exc:
                    logger.debug("dlq_shutdown_drain_failed: %s", exc)

            def health(self):
                from infrastructure.lifecycle import build_health

                return build_health(
                    self.name,
                    HealthState.HEALTHY if self._last_depth == 0 else HealthState.DEGRADED,
                    detail=f"depth={self._last_depth}, total_drained={self._total_drained}",
                    metrics={"depth": self._last_depth, "total_drained": self._total_drained},
                )

            def _loop(self) -> None:
                while not self._stop.wait(timeout=60.0):
                    stats = self._queue.stats()
                    self._last_depth = stats["size"]
                    if self._last_depth > 0:
                        logger.warning(
                            "DLQ depth: %d entries, %d dropped (lifetime)",
                            self._last_depth,
                            stats.get("dropped", 0),
                        )

        lifecycle.register(_DlqMonitor(dlq))

    def _register_processed_trade_cleanup(self, lifecycle: LifecycleManager) -> None:
        """Stop ProcessedTradeRepository auto-cleanup on lifecycle shutdown."""
        from infrastructure.lifecycle import HealthState, ManagedService, build_health

        repo = self._processed_trades

        class _ProcessedTradeCleanup(ManagedService):
            name = "oms.processed_trade_cleanup"

            def start(self) -> None:
                return

            def stop(self, timeout_seconds: float = 30.0) -> None:
                repo.stop_auto_cleanup(timeout_seconds=timeout_seconds)

            def health(self):
                return build_health(
                    self.name,
                    HealthState.HEALTHY,
                    detail="processed trade ledger active",
                )

        lifecycle.register(_ProcessedTradeCleanup())

    def _replay_log_into_oms(self) -> None:
        """Replay persisted ORDER_UPDATED/TRADE events to rebuild OMS state.

        Replay invokes the OMS handlers directly, which in turn publishes
        ``TRADE_APPLIED`` for accepted trades. During replay, the event bus
        suppresses handler dispatch (via ``replay_mode``), so we must
        directly invoke the position manager to ensure positions are rebuilt.
        """
        if self._event_log is None:
            return
        # A3: Defensive check - event_bus should always be initialized
        if self._event_bus is None:
            logger.warning("Event bus is None, skipping replay mode setup")
            return
        logger.info("Replaying event log into OMS")
        count = 0
        # A3: Enable replay mode to prevent TRADE_APPLIED dispatch during replay
        # (which would cause PositionManager to double-count trades)
        replay_was_enabled = self._event_bus.replay_mode
        self._event_bus.set_replay_mode(True)
        # Prevent re-logging events while rebuilding state.
        logging_was_enabled = self._event_bus.logging_enabled
        self._event_bus.set_logging_enabled(False)
        try:
            for event in self._event_log.replay(
                event_types={EventType.ORDER_UPDATED.value, EventType.TRADE.value}
            ):  # P1-3: Migrated to EventType enum
                if (
                    event.event_type == EventType.ORDER_UPDATED.value
                ):  # P1-3: Migrated to EventType enum
                    self._order_manager.on_order_update(event)
                elif event.event_type == EventType.TRADE.value:  # P1-3: Migrated to EventType enum
                    self._order_manager.on_trade(event)
                    # A3: During replay, TRADE_APPLIED events are suppressed by
                    # the event bus. Directly invoke position manager to rebuild
                    # positions from replayed trades.
                    self._position_manager.on_trade_applied(event)
                count += 1
        finally:
            self._event_bus.set_logging_enabled(logging_was_enabled)
            self._event_bus.set_replay_mode(replay_was_enabled)
        logger.info("Replayed %d events into OMS", count)

    # ── Graceful shutdown (B2 fix) ──────────────────────────────────────

    # ManagedService protocol attributes
    name: str = "oms.trading_context"
    _shutdown_gateway: Any | None = None  # Injectable gateway for testing
    _shutdown_in_progress: bool = False

    async def shutdown(
        self,
        cancel_orders: bool = True,
        gateway: Any | None = None,
    ) -> dict:
        """Graceful shutdown sequence.

        Sequence:
            1. Halt new order placement (set kill_switch)
            2. Cancel all open orders at broker
            3. Flush event log to disk
            4. Stop async bus workers
            5. Emit SYSTEM_SHUTDOWN event
            6. Close broker connections (via gateway)

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
        if self._shutdown_in_progress:
            logger.debug("TradingContext.shutdown: already in progress, skipping")
            return {
                "orders_cancelled": 0,
                "orders_failed": 0,
                "event_log_flushed": False,
                "connections_closed": 0,
            }
        self._shutdown_in_progress = True

        result = {
            "orders_cancelled": 0,
            "orders_failed": 0,
            "event_log_flushed": False,
            "connections_closed": 0,
        }

        # Step 1: Halt new order placement
        try:
            self._risk_manager.set_kill_switch(True)
            logger.info("TradingContext: kill switch activated")
        except Exception as exc:
            logger.warning("TradingContext: kill_switch activation failed: %s", exc)

        # Step 2: Cancel all open orders
        if cancel_orders:
            effective_gateway = gateway or self._shutdown_gateway
            cancel_result = self.cancel_all_open_orders(gateway=effective_gateway)
            result["orders_cancelled"] = cancel_result["orders_cancelled"]
            result["orders_failed"] = cancel_result["orders_failed"]
            logger.info(
                "TradingContext: order cancellation complete — cancelled=%d, failed=%d",
                result["orders_cancelled"],
                result["orders_failed"],
            )

        # Step 3: Flush event log to disk
        if self._event_log is not None:
            try:
                # BufferedEventLog has flush(), base EventLog does not
                if hasattr(self._event_log, "flush"):
                    self._event_log.flush()
                self._event_log.close()
                result["event_log_flushed"] = True
                logger.info("TradingContext: event log flushed and closed")
            except Exception as exc:
                logger.warning("TradingContext: event_log flush/close failed: %s", exc)

        # Step 4: Emit SYSTEM_SHUTDOWN event
        try:
            self._event_bus.publish(
                DomainEvent.now(
                    EventType.SYSTEM_SHUTDOWN.value,
                    payload={
                        "service_name": self.name,
                        "detail": "shutdown_complete",
                        "orders_cancelled": result["orders_cancelled"],
                        "orders_failed": result["orders_failed"],
                    },
                    source="TradingContext",
                )
            )
        except Exception as exc:
            logger.warning("TradingContext: SYSTEM_SHUTDOWN event publish failed: %s", exc)

        return result

    def cancel_all_open_orders(
        self,
        gateway: Any | None = None,
        timeout_per_order: float = 5.0,
    ) -> dict:
        """Cancel all open orders, optionally via a broker gateway.

        For each OPEN order in the OMS:
            1. If gateway is provided, call gateway.cancel_order()
            2. Update local order status to CANCELLED
            3. Collect success/failure

        Args:
            gateway: MarketDataGateway with cancel_order() method.
            timeout_per_order: Max seconds per cancellation (documented
                              for future async use).

        Returns:
            dict with:
                - orders_cancelled: count of successful cancellations
                - orders_failed: count of failed cancellations
                - failed_order_ids: list of order IDs that failed
        """
        from domain import OrderStatus

        result = {
            "orders_cancelled": 0,
            "orders_failed": 0,
            "failed_order_ids": [],
        }

        open_orders = [o for o in self._order_manager.get_orders() if o.status == OrderStatus.OPEN]

        if not open_orders:
            logger.debug("TradingContext: no open orders to cancel")
            return result

        logger.info("TradingContext: cancelling %d open orders", len(open_orders))

        for order in open_orders:
            try:
                # Try broker cancellation first if gateway available
                if gateway is not None:
                    try:
                        cancel_response = gateway.cancel_order(order.order_id)
                        if not getattr(cancel_response, "success", False):
                            msg = getattr(cancel_response, "message", "unknown")
                            logger.error(
                                "TradingContext: broker cancel failed for %s: %s",
                                order.order_id,
                                msg,
                            )
                            result["orders_failed"] += 1
                            result["failed_order_ids"].append(order.order_id)
                            continue
                    except Exception as exc:
                        logger.error(
                            "TradingContext: gateway.cancel_order(%s) raised: %s: %s",
                            order.order_id,
                            type(exc).__name__,
                            exc,
                        )
                        result["orders_failed"] += 1
                        result["failed_order_ids"].append(order.order_id)
                        continue

                # Local cancellation (always attempted, even if broker
                # cancel failed — we want local state to reflect intent)
                cancel_result = self._order_manager.cancel_order(order.order_id)
                if cancel_result.success:
                    result["orders_cancelled"] += 1
                else:
                    logger.warning(
                        "TradingContext: local cancel failed for %s: %s",
                        order.order_id,
                        cancel_result.error,
                    )
                    result["orders_failed"] += 1
                    result["failed_order_ids"].append(order.order_id)

            except Exception as exc:
                logger.error(
                    "TradingContext: unexpected error cancelling %s: %s: %s",
                    order.order_id,
                    type(exc).__name__,
                    exc,
                )
                result["orders_failed"] += 1
                result["failed_order_ids"].append(order.order_id)

        return result

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
            import asyncio

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self.shutdown(cancel_orders=True, gateway=self._shutdown_gateway)
                    )
                finally:
                    loop.close()
            except RuntimeError:
                self._sync_shutdown()
        except Exception as exc:
            logger.exception(
                "TradingContext.stop: shutdown failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    def _sync_shutdown(self) -> dict:
        """Synchronous shutdown path when async is unavailable.

        Performs the same steps as shutdown() but without async
        bus management.
        """
        result = {
            "orders_cancelled": 0,
            "orders_failed": 0,
            "event_log_flushed": False,
            "connections_closed": 0,
        }

        # Step 1: Kill switch
        try:
            self._risk_manager.set_kill_switch(True)
        except Exception as exc:
            logger.warning("TradingContext: kill_switch activation failed: %s", exc)

        # Step 2: Cancel open orders
        cancel_result = self.cancel_all_open_orders(gateway=self._shutdown_gateway)
        result["orders_cancelled"] = cancel_result["orders_cancelled"]
        result["orders_failed"] = cancel_result["orders_failed"]

        # Step 3: Flush event log
        if self._event_log is not None:
            try:
                # BufferedEventLog has flush(), base EventLog does not
                if hasattr(self._event_log, "flush"):
                    self._event_log.flush()
                self._event_log.close()
                result["event_log_flushed"] = True
            except Exception as exc:
                logger.warning("TradingContext: event_log flush/close failed: %s", exc)

        # Step 4: Emit SYSTEM_SHUTDOWN event
        try:
            self._event_bus.publish(
                DomainEvent.now(
                    EventType.SYSTEM_SHUTDOWN.value,
                    payload={
                        "service_name": self.name,
                        "detail": "shutdown_complete",
                        "orders_cancelled": result["orders_cancelled"],
                        "orders_failed": result["orders_failed"],
                    },
                    source="TradingContext",
                )
            )
        except Exception as exc:
            logger.warning("TradingContext: SYSTEM_SHUTDOWN event publish failed: %s", exc)

        return result

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
