"""Trading context — wires EventBus, OMS, Position and Risk managers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from brokers.common.event_bus import (
    DeadLetterQueue,
    EventBus,
    ProcessedTradeRepository,
)
from brokers.common.event_log import EventLog
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.oms.order_manager import OrderManager
from brokers.common.oms.position_manager import PositionManager
from brokers.common.oms.risk_manager import RiskConfig, RiskManager

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
        reconciliation_interval_seconds: float = 300.0,
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
        self._position_manager = position_manager or PositionManager(
            event_bus=self._event_bus,
            processed_trade_repository=self._processed_trades,
            metrics=self._metrics,
        )
        self._risk_manager = risk_manager or RiskManager(
            self._position_manager,
            risk_config or RiskConfig(),
            capital_fn or (lambda: Decimal("1000000")),
        )
        self._order_manager = order_manager or OrderManager(
            event_bus=self._event_bus,
            risk_manager=self._risk_manager,
            processed_trade_repository=self._processed_trades,
            metrics=self._metrics,
        )

        # Wire managers to the event bus.
        self._event_bus.subscribe("ORDER_UPDATED", self._order_manager.on_order_update)
        # The OMS is the sole gatekeeper for trade idempotency. The
        # position manager subscribes to TRADE_APPLIED (a downstream
        # event the OMS publishes only after a trade has been accepted)
        # rather than to raw TRADE events. This guarantees that
        # duplicate websocket fills cannot double-count positions.
        self._event_bus.subscribe("TRADE", self._order_manager.on_trade)
        self._event_bus.subscribe("TRADE_APPLIED", self._position_manager.on_trade_applied)

        # Reconciliation
        self._reconciliation_service = reconciliation_service
        self._reconciliation_interval = reconciliation_interval_seconds
        self._recon_thread: threading.Thread | None = None
        self._recon_stop_event = threading.Event()

        if replay_events and self._event_log is not None:
            self._replay_log_into_oms()

        # Start periodic reconciliation if service provided
        if self._reconciliation_service is not None and self._reconciliation_interval > 0:
            self._start_reconciliation_timer()

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
        """Run reconciliation immediately (called by timer or manually)."""
        if self._reconciliation_service is None:
            return None
        try:
            report = self._reconciliation_service.reconcile(
                local_orders=self._order_manager.get_all_orders(),
                local_positions=self._position_manager.get_positions_as_dicts(),
            )
            if hasattr(report, "has_drift") and report.has_drift:
                logger.warning(
                    "Reconciliation found %d drift items (high: %d)",
                    len(report.drift_items),
                    report.high_severity_count,
                )
            return report
        except Exception as exc:
            logger.error("Reconciliation failed: %s", exc)
            return None

    def stop_reconciliation(self) -> None:
        """Stop the periodic reconciliation timer."""
        self._recon_stop_event.set()
        if self._recon_thread is not None and self._recon_thread.is_alive():
            self._recon_thread.join(timeout=5)

    def _start_reconciliation_timer(self) -> None:
        """Start background thread for periodic reconciliation."""
        self._recon_stop_event.clear()
        self._recon_thread = threading.Thread(
            target=self._reconciliation_loop,
            daemon=True,
            name="reconciliation-timer",
        )
        self._recon_thread.start()
        logger.info(
            "Reconciliation timer started (interval=%ss)",
            self._reconciliation_interval,
        )

    def _reconciliation_loop(self) -> None:
        """Background loop that runs reconciliation periodically."""
        while not self._recon_stop_event.is_set():
            # Wait for interval or stop signal
            if self._recon_stop_event.wait(timeout=self._reconciliation_interval):
                break
            self.run_reconciliation()

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
            for event in self._event_log.replay(event_types={"ORDER_UPDATED", "TRADE"}):
                if event.event_type == "ORDER_UPDATED":
                    self._order_manager.on_order_update(event)
                elif event.event_type == "TRADE":
                    self._order_manager.on_trade(event)
                count += 1
        finally:
            self._event_bus._logging_enabled = logging_was_enabled
        logger.info("Replayed %d events into OMS", count)
