"""Lifecycle helper services for TradingContext.

Extracted from context.py to reduce god-object size. These lightweight
services participate in the LifecycleManager for deterministic start/stop.
"""

from __future__ import annotations

import logging
import threading

from domain.ports import DeadLetterQueuePort, ProcessedTradeRepositoryPort
from domain.ports.lifecycle import LifecycleManagerPort

logger = logging.getLogger(__name__)


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


def register_daily_pnl_reset(lifecycle: LifecycleManagerPort, risk_manager) -> None:
    """Auto-wire a DailyPnlResetScheduler so daily PnL is always reset.

    This is the SINGLE registration point for the scheduler.
    BrokerService no longer registers a duplicate (fixed P2-1).
    """
    from application.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler

    scheduler = DailyPnlResetScheduler(risk_manager=risk_manager)
    lifecycle.register(scheduler)


def register_dlq_monitor(lifecycle: LifecycleManagerPort, dead_letter_queue) -> None:
    """Register a lightweight DLQ depth monitor with the lifecycle."""
    lifecycle.register(DlqMonitorService(dead_letter_queue))


def register_processed_trade_cleanup(lifecycle: LifecycleManagerPort, processed_trades) -> None:
    """Stop ProcessedTradeRepository auto-cleanup on lifecycle shutdown."""
    lifecycle.register(ProcessedTradeCleanupService(processed_trades))
