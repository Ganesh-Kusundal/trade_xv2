"""Trading context — wires EventBus, OMS, Position and Risk managers."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any  # Only for signal handler frame type

from application.oms.event_log_replay import EventLogReplayService
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.shutdown_coordinator import ShutdownCoordinator

# The concrete TradingOrchestrator was previously imported here (guarded by
# a try/except "to avoid circular dependency") but was dead code: neither
# the import nor its _HAS_ORCHESTRATOR flag were ever read anywhere in this
# file. All real typing/usage already goes through the ITradingOrchestrator
# protocol below, which is also what makes this module safe from depending
# on application.trading (and transitively analytics.*) at all — see the
# "Trading does not import Analytics (D2)" import-linter contract.
from application.oms.protocols import (
    IBrokerGateway,
    IReconciliationService,
    ITradingOrchestrator,
)
from application.oms.reconciliation_service import ReconciliationService
from application.oms.risk_manager import RiskConfig, RiskManager
from domain.constants import PHANTOM_CAPITAL_INR, RECONCILIATION_INTERVAL_SECONDS
from domain.events.types import DomainEvent, EventType
from domain.ports import (
    DeadLetterQueuePort,
    EventBusPort,
    EventLogPort,
    EventMetricsPort,
    ExecutionLedgerPort,
    MetricsRegistryPort,
    OrderStorePort,
    ProcessedTradeRepositoryPort,
)
from domain.ports.lifecycle import LifecycleManagerPort

logger = logging.getLogger(__name__)


# ── Managed services extracted to module level for testability ────────────────


class DlqMonitorService:
    """Lightweight DLQ depth monitor — logs depth periodically, drains on shutdown.

    Registered with :class:`LifecycleManager` so the DLQ is drained
    deterministically and its entries are visible in logs on shutdown.
    """

    name = "oms.dlq_monitor"

    def __init__(self, queue: DeadLetterQueuePort) -> None:
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
        from domain.lifecycle_health import HealthState, build_health

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


class ProcessedTradeCleanupService:
    """Stops ProcessedTradeRepository auto-cleanup on lifecycle shutdown."""

    name = "oms.processed_trade_cleanup"

    def __init__(self, repo: ProcessedTradeRepositoryPort) -> None:
        self._repo = repo

    def start(self) -> None:
        return

    def stop(self, timeout_seconds: float = 30.0) -> None:
        self._repo.stop_auto_cleanup(timeout_seconds=timeout_seconds)

    def health(self):
        from domain.lifecycle_health import HealthState, build_health

        return build_health(
            self.name,
            HealthState.HEALTHY,
            detail="processed trade ledger active",
        )


from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class CancellationResult:
    """Typed result for cancel_all_open_orders."""

    orders_cancelled: int = 0
    orders_failed: int = 0
    failed_order_ids: tuple[str, ...] = ()

    def __getitem__(self, key: str) -> int | tuple[str, ...]:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None


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
        event_bus: EventBusPort | None = None,
        event_log: EventLogPort | None = None,
        order_manager: OrderManager | None = None,
        position_manager: PositionManager | None = None,
        risk_manager: RiskManager | None = None,
        risk_config: RiskConfig | None = None,
        capital_fn: Callable[[], Decimal] | None = None,
        replay_events: bool = True,
        reconciliation_service: IReconciliationService | None = None,
        reconciliation_interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
        processed_trade_repository: ProcessedTradeRepositoryPort | None = None,
        metrics: EventMetricsPort | None = None,
        metrics_registry: MetricsRegistryPort | None = None,
        dead_letter_queue: DeadLetterQueuePort | None = None,
        orchestrator: ITradingOrchestrator | None = None,
        durable_order_store: OrderStorePort | None = None,
        execution_ledger: ExecutionLedgerPort | None = None,
        enable_durable_orders: bool | None = None,
    ) -> None:
        self._event_log = event_log
        self._metrics = metrics
        self._metrics_registry = metrics_registry
        self._dead_letter_queue = dead_letter_queue

        # If the caller supplied an event bus, attach observability to it
        # silently; otherwise build a bus that has both observability hooks
        # attached.
        if event_bus is None:
            # The event bus is a required collaborator.  It is injected by the
            # composition root (cli / api / runtime) or by the test harness —
            # ``application`` must not construct infrastructure objects.
            raise ValueError(
                "TradingContext requires an event_bus; inject a concrete "
                "EventBus via the composition root or test harness."
            )
        self._event_bus = event_bus
        # ENG-010: attach durable log to bus when composition root built them
        # separately (CLI/API often create the bus first, then the EventLog).
        if (
            event_log is not None
            and hasattr(self._event_bus, "set_event_log")
            and getattr(self._event_bus, "_event_log", None) is None
        ):
            self._event_bus.set_event_log(event_log)

        self._processed_trades = processed_trade_repository
        # Enable the self-cleaning thread. It runs as a daemon
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
            metrics_registry=self._metrics_registry,
            order_store=durable_order_store,
            execution_ledger=execution_ledger,
        )

        # Wire managers to the event bus.
        self._event_bus.subscribe(
            EventType.ORDER_UPDATED.value, self._order_manager.on_order_update
        )
        # The OMS is the sole gatekeeper for trade idempotency. The
        # position manager subscribes to TRADE_APPLIED (a downstream
        # event the OMS publishes only after a trade has been accepted)
        # rather than to raw TRADE events. This guarantees that
        # duplicate websocket fills cannot double-count positions.
        self._event_bus.subscribe(
            EventType.TRADE.value, self._order_manager.on_trade
        )
        self._event_bus.subscribe(
            EventType.TRADE_APPLIED.value, self._position_manager.on_trade_applied
        )

        # R2 / Q1: feed live position PnL into the risk engine so the daily
        # loss limit and rolling loss circuit breaker actually observe fills
        # and mark-to-market. update_daily_pnl() stores the absolute daily PnL
        # and records the delta internally, so we pass the total book PnL
        # (realized + unrealized) computed from the position manager's book.
        # This is the composition root, so no new import cycle is introduced.
        self._event_bus.subscribe(
            EventType.POSITION_UPDATED.value, self._feed_daily_pnl
        )
        self._event_bus.subscribe(
            EventType.POSITION_CLOSED.value, self._feed_daily_pnl
        )

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

        self._shutdown_coordinator = ShutdownCoordinator(
            risk_manager=self._risk_manager,
            order_manager=self._order_manager,
            event_bus=self._event_bus,
            event_log=self._event_log,
        )
        self._replay_service = EventLogReplayService(
            event_bus=self._event_bus,
            event_log=self._event_log,
            order_manager=self._order_manager,
            position_manager=self._position_manager,
        )

        if replay_events and self._event_log is not None:
            self._replay_log_into_oms()

        self._orchestrator: ITradingOrchestrator | None = orchestrator

        # Shutdown thread-safety: _shutdown_lock prevents concurrent shutdown
        # attempts from both passing the guard simultaneously (TD-12).
        self._shutdown_lock = threading.Lock()
        self._shutdown_in_progress = False

    def attach_lifecycle(self, lifecycle: LifecycleManagerPort) -> None:
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

        # Register TradingContext itself as a ManagedService so
        # it participates in deterministic start/stop via the lifecycle.
        lifecycle.register(self)

        if self._orchestrator is not None:
            lifecycle.register(self._orchestrator)
            logger.info("TradingOrchestrator registered with lifecycle")

    @property
    def event_bus(self) -> EventBusPort:
        return self._event_bus

    @property
    def event_log(self) -> EventLogPort | None:
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
    def metrics(self) -> EventMetricsPort | None:
        return self._metrics

    @property
    def dead_letter_queue(self) -> DeadLetterQueuePort:
        return self._dead_letter_queue

    @property
    def processed_trade_repository(self) -> ProcessedTradeRepositoryPort:
        return self._processed_trades

    @property
    def orchestrator(self) -> Any | None:
        """Access the TradingOrchestrator if configured."""
        return self._orchestrator

    @property
    def command_dispatcher(self) -> Any | None:
        """CQRS CommandDispatcher if attached by the composition root (ADR-012).

        The composition root (tradex.session / runtime factory) may set this
        attribute after construction; TradingContext does not build it itself
        to avoid an application -> runtime dependency cycle.
        """
        return getattr(self, "_command_dispatcher", None)

    @property
    def query_dispatcher(self) -> Any | None:
        """CQRS QueryDispatcher if attached by the composition root (ADR-012)."""
        return getattr(self, "_query_dispatcher", None)

    def health(self) -> dict[str, Any]:
        """Snapshot of observability state for the SRE / alerting layer."""
        order_store = getattr(self._order_manager, "_order_store", None)
        return {
            "metrics": self._metrics.snapshot() if self._metrics is not None else {},
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

    def _feed_daily_pnl(self, event: DomainEvent | None = None) -> None:
        """Push the current book PnL into the risk engine.

        Wires the position book to :meth:`RiskManager.update_daily_pnl` so the
        daily loss limit and loss circuit breaker observe live fills and
        mark-to-market. Called on every ``POSITION_UPDATED`` / ``POSITION_CLOSED``
        event published by the position manager.

        The risk engine stores the absolute daily PnL and derives the delta
        internally, so we pass the total book PnL (sum of realized + unrealized
        across all positions). Passing the absolute total on each tick yields
        the correct incremental delta for the loss circuit breaker.
        """
        if self._risk_manager is None:
            return
        positions = self._position_manager.get_positions()
        total = Decimal("0")
        for p in positions:
            realized = getattr(p, "realized_pnl", Decimal("0")) or Decimal("0")
            unrealized = getattr(p, "unrealized_pnl", Decimal("0")) or Decimal("0")
            total += realized + unrealized
        try:
            self._risk_manager.update_daily_pnl(total)
        except Exception:  # pragma: no cover - defensive: never block the bus
            logger.exception("daily_pnl_feed_failed")

    def _register_daily_pnl_reset(self, lifecycle: LifecycleManagerPort) -> None:
        """Auto-wire a DailyPnlResetScheduler so daily PnL is always reset.

        This is the SINGLE registration point for the scheduler.
        BrokerService no longer registers a duplicate (fixed P2-1).
        """
        from application.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler

        scheduler = DailyPnlResetScheduler(risk_manager=self._risk_manager)
        lifecycle.register(scheduler)

    def _register_dlq_monitor(self, lifecycle: LifecycleManagerPort) -> None:
        """Register a lightweight DLQ depth monitor with the lifecycle."""
        lifecycle.register(DlqMonitorService(self._dead_letter_queue))

    def _register_processed_trade_cleanup(self, lifecycle: LifecycleManagerPort) -> None:
        """Stop ProcessedTradeRepository auto-cleanup on lifecycle shutdown."""
        lifecycle.register(ProcessedTradeCleanupService(self._processed_trades))

    def _replay_log_into_oms(self) -> None:
        """Replay persisted ORDER_UPDATED/TRADE events to rebuild OMS state.

        Delegates to :class:`EventLogReplayService` which handles bus
        replay-mode toggling and direct position-manager invocation.
        """
        if self._event_log is None:
            return
        if self._event_bus is None:
            logger.warning("Event bus is None, skipping replay mode setup")
            return
        self._replay_service.replay()

    # ── Graceful shutdown (B2 fix) ──────────────────────────────────────

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
                from runtime.event_loop import run_coro_sync

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
