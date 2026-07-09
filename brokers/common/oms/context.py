"""Trading context — wires EventBus, OMS, Position and Risk managers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from brokers.common.core.constants import PHANTOM_CAPITAL_INR, RECONCILIATION_INTERVAL_SECONDS
from infrastructure.event_bus import (
    DeadLetterQueue,
    EventBus,
    EventType,
    ProcessedTradeRepository,
)
from src.domain.ports.event_log import EventLogPort as EventLog
from brokers.common.lifecycle import LifecycleManager
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.reconciliation_service import ReconciliationService
from application.oms.risk_manager import RiskConfig, RiskManager

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
        self._event_bus.subscribe(EventType.ORDER_UPDATED, self._order_manager.on_order_update)
        # The OMS is the sole gatekeeper for trade idempotency. The
        # position manager subscribes to TRADE_APPLIED (a downstream
        # event the OMS publishes only after a trade has been accepted)
        # rather than to raw TRADE events. This guarantees that
        # duplicate websocket fills cannot double-count positions.
        self._event_bus.subscribe(EventType.TRADE, self._order_manager.on_trade)
        self._event_bus.subscribe(EventType.TRADE_APPLIED, self._position_manager.on_trade_applied)

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

    def attach_lifecycle(self, lifecycle: LifecycleManager) -> None:
        """Register the context's managed services with a lifecycle.

        Callers that own a :class:`LifecycleManager` (the CLI, the TUI,
        the live gateway) MUST call this so the reconciliation service
        (and any future managed services) participate in deterministic
        start/stop.
        """
        if self._reconciliation_service is not None:
            lifecycle.register(self._reconciliation_service)
        # REF-19: ensure the trade-id ledger's cleanup thread is
        # stopped deterministically when the lifecycle drains.
        self._processed_trades.stop_auto_cleanup()

    def attach_reconciliation_service(
        self,
        broker_service: Any,
        lifecycle: LifecycleManager | None = None,
        interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    ) -> None:
        """Attach a broker-specific reconciliation service to the OMS.

        Phase 1.4: replaces the legacy monkey-patch
        (``dhan_reconciliation._oms = order_manager``) with an explicit,
        fail-closed setter. ``broker_service`` must already be wired with
        the OMS OrderManager (the ``DhanReconciliationService`` only needs
        it for ``auto_repair=True``; drift detection itself works without
        an OMS reference).

        If a lifecycle is provided, the new ReconciliationService wrapper
        is registered with it so it is drained on shutdown. Calling this
        twice replaces the existing service (the previous one is stopped
        first to avoid leaking its background thread).
        """
        if self._reconciliation_service is not None:
            try:
                self._reconciliation_service.stop()
            except Exception as exc:
                logger.debug("prior_reconciliation_stop_failed: %s", exc)
            self._reconciliation_service = None
        self._reconciliation_service = ReconciliationService(
            order_manager=self._order_manager,
            position_manager=self._position_manager,
            reconciliation_service=broker_service,
            interval_seconds=interval_seconds,
            event_bus=self._event_bus,
        )
        if lifecycle is not None:
            lifecycle.register(self._reconciliation_service)

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

    def _replay_log_into_oms(self) -> None:
        """Replay persisted events to rebuild OMS state.

        Replays three event types so the OMS book is exactly where it
        was before the crash:

        * ``ORDER_PLACED`` — calls :meth:`OrderManager.upsert_order` so
          the order is in the book even if the WS update never arrived.
          This closes the crash-recovery gap where an order placed just
          before a crash would be lost on restart.
        * ``ORDER_UPDATED`` — invokes the existing OMS handler.
        * ``TRADE`` — invokes the existing OMS handler; downstream
          ``TRADE_APPLIED`` events are published automatically by
          :meth:`OrderManager.record_trade` and consumed by the
          position manager.

        Replay invokes the OMS handlers directly, so the event bus is
        temporarily muted (``_logging_enabled = False``) to avoid
        double-logging the replayed events.
        """
        if self._event_log is None:
            return
        logger.info("Replaying event log into OMS")
        count = 0
        # Prevent re-logging events while rebuilding state.
        logging_was_enabled = self._event_bus._logging_enabled
        self._event_bus._logging_enabled = False
        try:
            for event in self._event_log.replay(
                event_types={"ORDER_PLACED", "ORDER_UPDATED", "TRADE"},
            ):
                if event.event_type == "ORDER_PLACED":
                    order = event.payload.get("order")
                    if order is not None:
                        # upsert_order is idempotent: re-inserting an
                        # existing order replaces it in place.
                        self._order_manager.upsert_order(order)
                elif event.event_type == "ORDER_UPDATED":
                    self._order_manager.on_order_update(event)
                elif event.event_type == "TRADE":
                    self._order_manager.on_trade(event)
                count += 1
        finally:
            self._event_bus._logging_enabled = logging_was_enabled
        logger.info("Replayed %d events into OMS", count)
