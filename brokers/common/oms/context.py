"""Trading context — wires EventBus, OMS, Position and Risk managers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from brokers.common.core.constants import PHANTOM_CAPITAL_INR, RECONCILIATION_INTERVAL_SECONDS
from brokers.common.event_bus import (
    DeadLetterQueue,
    EventBus,
    EventType,
    ProcessedTradeRepository,
)
from brokers.common.event_bus.async_event_bus import AsyncEventBus
from brokers.common.event_bus.factory import (
    AsyncEventBusFactory,
    AsyncPublishAdapter,
    async_publish_wrapper,
)
from brokers.common.event_log import EventLog
from brokers.common.lifecycle import LifecycleManager
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.oms.order_manager import OrderManager
from brokers.common.oms.position_manager import PositionManager
from brokers.common.oms.reconciliation_service import ReconciliationService
from brokers.common.oms.risk_manager import RiskConfig, RiskManager

# P1-Phase 1: Optional import for TradingOrchestrator
# Import only when needed to avoid circular dependency
try:
    from brokers.common.orchestrator import TradingOrchestrator
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
        event_log: EventLog | None = None,
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
        async_bus: AsyncEventBus | None = None,  # AsyncEventBus integration
    ) -> None:
        self._event_log = event_log
        self._metrics = metrics or EventMetrics()
        self._dead_letter_queue = dead_letter_queue or DeadLetterQueue()

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

        # AsyncEventBus integration (Phase 1: opt-in via async_bus parameter)
        # Migration Guide:
        #   Phase 1: Pass async_bus explicitly for async event processing
        #   Phase 2: Factory creates async bus based on USE_ASYNC_EVENT_BUS env var
        #   Phase 3: Async becomes default, sync available via force_sync=True
        self._async_bus = async_bus
        self._is_async_bus = async_bus is not None
        
        # Create async publish wrapper if async bus is available
        # This provides a uniform async publish() API for gradual migration
        if self._is_async_bus:
            self._async_publisher = async_publish_wrapper(
                self._async_bus, is_async=True
            )
            logger.info("TradingContext: AsyncEventBus enabled")
        else:
            self._async_publisher = None

        self._processed_trades = (
            processed_trade_repository or ProcessedTradeRepository()
        )
        # REF-19: enable the self-cleaning thread. It runs as a daemon
        # so it does not block process exit; callers that own a
        # LifecycleManager can stop it deterministically via
        # attach_lifecycle() below.
        self._processed_trades.attach_auto_cleanup()
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
        )

        # Wire managers to the event bus.
        self._event_bus.subscribe(EventType.ORDER_UPDATED.value, self._order_manager.on_order_update)  # P1-3: Migrated to EventType enum
        # The OMS is the sole gatekeeper for trade idempotency. The
        # position manager subscribes to TRADE_APPLIED (a downstream
        # event the OMS publishes only after a trade has been accepted)
        # rather than to raw TRADE events. This guarantees that
        # duplicate websocket fills cannot double-count positions.
        self._event_bus.subscribe(EventType.TRADE.value, self._order_manager.on_trade)  # P1-3: Migrated to EventType enum
        self._event_bus.subscribe(EventType.TRADE_APPLIED.value, self._position_manager.on_trade_applied)  # P1-3: Migrated to EventType enum

        # Reconciliation: an externally-owned ReconciliationService
        # (a ManagedService) is created here so it can be registered
        # with the lifecycle and drained on shutdown. The previous
        # implementation started an anonymous daemon thread inside
        # __init__ and never stopped it.
        self._reconciliation_service: ReconciliationService | None = None
        if (
            reconciliation_service is not None
            and reconciliation_interval_seconds > 0
        ):
            self._reconciliation_service = ReconciliationService(
                order_manager=self._order_manager,
                position_manager=self._position_manager,
                reconciliation_service=reconciliation_service,
                interval_seconds=reconciliation_interval_seconds,
                event_bus=self._event_bus,
            )

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
        # REF-19: ensure the trade-id ledger's cleanup thread is
        # stopped deterministically when the lifecycle drains.
        self._processed_trades.stop_auto_cleanup()
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
        
        # P1-Phase 1: Register orchestrator for start/stop
        if self._orchestrator is not None:
            lifecycle.register(self._orchestrator)
            logger.info("TradingOrchestrator registered with lifecycle")

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def event_log(self) -> EventLog | None:
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

    @property
    def async_bus(self) -> AsyncEventBus | None:
        """Access the AsyncEventBus if configured.
        
        Returns None if sync EventBus is being used.
        Check is_async_bus before using this property.
        """
        return self._async_bus

    @property
    def is_async_bus(self) -> bool:
        """True if AsyncEventBus is configured, False if using sync EventBus."""
        return self._is_async_bus

    @property
    def async_publisher(self) -> AsyncPublishAdapter | None:
        """Access the async publish adapter if async bus is configured.
        
        This provides a uniform async publish() API that works with both
        sync and async buses. Returns None if only sync bus is available.
        
        Usage:
            if ctx.async_publisher:
                await ctx.async_publisher.publish("ORDER_PLACED", payload)
        """
        return self._async_publisher

    def health(self) -> dict[str, Any]:
        """Snapshot of observability state for the SRE / alerting layer."""
        return {
            "metrics": self._metrics.snapshot(),
            "dead_letter": self._dead_letter_queue.stats(),
            "trades": self._processed_trades.stats(),
            "event_log_errors": self._event_log.errors if self._event_log else 0,
        }

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

    async def start_async_bus(self) -> None:
        """Start the AsyncEventBus dispatch worker.
        
        This must be called before publishing events to the async bus.
        Typically called during application startup after all handlers
        are subscribed.
        
        No-op if async bus is not configured.
        
        Usage:
            ctx = TradingContext(async_bus=async_bus)
            # ... subscribe handlers ...
            await ctx.start_async_bus()
        """
        if self._async_bus is not None:
            await self._async_bus.start()
            logger.info("TradingContext: AsyncEventBus started")

    async def stop_async_bus(self, timeout_seconds: float = 10.0) -> None:
        """Stop the AsyncEventBus dispatch worker.
        
        Waits for pending events to be processed before returning.
        Call this during graceful shutdown.
        
        No-op if async bus is not configured.
        
        Parameters
        ----------
        timeout_seconds:
            Maximum time to wait for worker to stop (default 10s).
        """
        if self._async_bus is not None:
            await self._async_bus.stop()
            logger.info("TradingContext: AsyncEventBus stopped")

    async def wait_async_bus_completion(
        self, timeout_seconds: float | None = None
    ) -> bool:
        """Wait for all queued async events to be processed.
        
        Parameters
        ----------
        timeout_seconds:
            Maximum time to wait (seconds). None = wait forever.
        
        Returns
        -------
        bool:
            True if all events processed, False if timeout.
        """
        if self._async_bus is not None:
            return await self._async_bus.wait_for_completion(
                timeout=timeout_seconds
            )
        return True

    def get_async_bus_stats(self) -> dict | None:
        """Get AsyncEventBus statistics.
        
        Returns None if async bus is not configured.
        """
        if self._async_bus is not None:
            return self._async_bus.get_stats()
        return None

    def _register_daily_pnl_reset(self, lifecycle: LifecycleManager) -> None:
        """Auto-wire a DailyPnlResetScheduler so daily PnL is always reset.
        
        This is the SINGLE registration point for the scheduler.
        BrokerService no longer registers a duplicate (fixed P2-1).
        """
        from brokers.common.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler
        scheduler = DailyPnlResetScheduler(risk_manager=self._risk_manager)
        lifecycle.register(scheduler)

    def _register_dlq_monitor(self, lifecycle: LifecycleManager) -> None:
        """Register a lightweight DLQ depth monitor with the lifecycle.

        Periodically logs dead-letter queue depth so operators can alert
        on handler failures. On shutdown (stop), drains the DLQ and logs
        any remaining entries so they are not silently lost.
        """
        from brokers.common.event_bus import DeadLetterQueue
        from brokers.common.lifecycle import HealthState, ManagedService

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
                self._thread = threading.Thread(
                    target=self._loop, daemon=True, name="dlq-monitor"
                )
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
                from brokers.common.lifecycle import build_health
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

    def _replay_log_into_oms(self) -> None:
        """Replay persisted ORDER_UPDATED/TRADE events to rebuild OMS state.

        Replay invokes the OMS handlers directly, which in turn publishes
        ``TRADE_APPLIED`` for accepted trades; the position manager
        subscribes to that event in the bus, so no direct call is needed
        here.
        """
        if self._event_log is None:
            return
        logger.info("Replaying event log into OMS")
        count = 0
        # Prevent re-logging events while rebuilding state.
        logging_was_enabled = self._event_bus._logging_enabled
        self._event_bus._logging_enabled = False
        try:
            for event in self._event_log.replay(event_types={EventType.ORDER_UPDATED.value, EventType.TRADE.value}):  # P1-3: Migrated to EventType enum
                if event.event_type == EventType.ORDER_UPDATED.value:  # P1-3: Migrated to EventType enum
                    self._order_manager.on_order_update(event)
                elif event.event_type == EventType.TRADE.value:  # P1-3: Migrated to EventType enum
                    self._order_manager.on_trade(event)
                count += 1
        finally:
            self._event_bus._logging_enabled = logging_was_enabled
        logger.info("Replayed %d events into OMS", count)
