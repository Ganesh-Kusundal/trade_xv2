"""Reconciliation service — a ManagedService that periodically reconciles
the OMS state with the broker.

This module exists so the reconciliation timer can be registered with a
:class:`brokers.common.lifecycle.LifecycleManager` and drained on
shutdown — the previous in-context ad-hoc thread leaked across
process restarts.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.protocols import IReconciliationService
from domain.constants import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    MIN_SLEEP_SECONDS,
    RECONCILIATION_INTERVAL_SECONDS,
)
from domain.reconciliation import ReconciliationReport
from domain.ports import EventBusPort
from domain.lifecycle_health import HealthState, build_health
from domain.ports.lifecycle import ManagedServicePort
from application.observability import trace_operation

logger = logging.getLogger(__name__)


class ReconciliationService(ManagedServicePort):
    """Periodically reconciles OMS state with the broker.

    The service is a :class:`ManagedService` so it can be registered
    with a :class:`LifecycleManager` and drained deterministically on
    shutdown.

    Parameters
    ----------
    order_manager:
        The OMS whose state should be reconciled.
    position_manager:
        The position manager whose state should be reconciled.
    reconciliation_service:
        The actual reconcile() implementation. Typically a broker-
        specific adapter. Must have a ``reconcile(local_orders, local_positions)``
        method that returns a report with a ``has_drift`` attribute.
    interval_seconds:
        How often to run reconciliation.
    event_bus:
        Optional bus used to publish ``RECONCILIATION_COMPLETED`` events.
    """

    name: str = "oms.reconciliation"

    def __init__(
        self,
        order_manager: OrderManager,
        position_manager: PositionManager,
        reconciliation_service: IReconciliationService,
        interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
        event_bus: EventBusPort | None = None,
        on_first_success: Callable[[], None] | None = None,
        execution_engine: Any | None = None,
    ) -> None:
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._reconciliation_service = reconciliation_service
        # Minimum sleep so the loop can never busy-spin. Tests use
        # sub-second intervals; production should use ≥5s.
        self._interval = max(MIN_SLEEP_SECONDS, float(interval_seconds))
        self._event_bus = event_bus
        self._on_first_success = on_first_success
        self._execution_engine = execution_engine
        self._first_success_notified = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._immediate_request = threading.Event()
        self._last_run_at: float | None = None
        self._last_drift_count: int = 0
        self._last_error: str | None = None
        self._run_count = 0

    # ── ManagedService contract ──────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="reconciliation-timer")
        self._thread.start()
        logger.info("Reconciliation service started (interval=%.1fs)", self._interval)

    def stop(self, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        self._stop_event.set()
        self._immediate_request.set()
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning(
                    "Reconciliation service did not stop within %.1fs; "
                    "leaving the daemon to be reaped at process exit",
                    timeout_seconds,
                )
            self._thread = None
        logger.info("Reconciliation service stopped (ran %d times)", self._run_count)

    def health(self):  # type: ignore[override]
        if self._thread is None or not self._thread.is_alive():
            state = HealthState.STOPPED
            detail = "not running"
        elif self._last_error is not None:
            state = HealthState.DEGRADED
            detail = f"last error: {self._last_error}"
        else:
            state = HealthState.HEALTHY
            detail = f"ran {self._run_count} times; last_drift={self._last_drift_count}"
        return build_health(
            self.name,
            state,
            detail=detail,
            metrics={
                "run_count": self._run_count,
                "interval_seconds": self._interval,
                "last_drift_count": self._last_drift_count,
            },
        )

    # ── Public API ───────────────────────────────────────────────────────

    def request_reconciliation(self) -> None:
        """Signal the loop to run reconciliation at the next opportunity.

        Intended to be subscribed to hot-path events (TRADE_APPLIED,
        ORDER_UPDATED).  Multiple rapid calls coalesce into a single
        reconciliation run — the flag is cleared only when the loop
        picks it up.
        """
        self._immediate_request.set()

    @trace_operation("reconciliation.run_now")
    def run_now(self) -> ReconciliationReport | None:
        """Run reconciliation immediately."""
        return self._run_once()

    @property
    def last_run_at(self) -> float | None:
        return self._last_run_at

    @property
    def last_drift_count(self) -> int:
        return self._last_drift_count

    @property
    def run_count(self) -> int:
        return self._run_count

    # ── Internals ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Wake on interval OR immediate event-driven request
            self._immediate_request.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            self._immediate_request.clear()
            try:
                self._run_once()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.error("Reconciliation loop error: %s", exc)

    def _run_ledger_shadow_compare(self) -> None:
        lifecycle = self._order_manager.lifecycle if hasattr(self._order_manager, 'lifecycle') else None
        ledger = lifecycle.execution_ledger if lifecycle is not None and hasattr(lifecycle, 'execution_ledger') else None
        if ledger is None:
            recorder = self._order_manager.trade_recorder if hasattr(self._order_manager, 'trade_recorder') else None
            ledger = recorder.execution_ledger if recorder is not None and hasattr(recorder, 'execution_ledger') else None
        try:
            from application.oms.ledger_shadow import compare_ledger_vs_positions

            shadow = compare_ledger_vs_positions(ledger, self._position_manager)
            if shadow.enabled and shadow.has_drift:
                logger.warning(
                    "ledger_shadow_parity_failed drifts=%d compared=%d",
                    len(shadow.drifts),
                    shadow.compared_symbols,
                )
        except Exception as exc:
            logger.debug("ledger_shadow_compare_skipped: %s", exc)

    def _run_once(self) -> ReconciliationReport | None:
        report = None
        try:
            report = self._reconciliation_service.reconcile(
                local_orders=self._order_manager.get_orders(),
                local_positions=self._position_manager.get_positions(),
            )
            # I6: apply drift inside ExecutionEngine, not in broker adapter
            if self._execution_engine is not None and hasattr(report, "drift_items"):
                broker_order_list = getattr(report, "broker_order_list", [])
                broker_position_list = getattr(report, "broker_position_list", [])
                broker_funds = getattr(report, "broker_funds", None)
                self._execution_engine.apply_mass_status(
                    orders=broker_order_list,
                    positions=broker_position_list,
                    funds=broker_funds,
                )
            self._run_ledger_shadow_compare()
            if hasattr(report, "has_drift") and report.has_drift:
                self._last_drift_count = len(getattr(report, "drift_items", []))
                logger.warning(
                    "Reconciliation found %d drift items (high: %d)",
                    self._last_drift_count,
                    getattr(report, "high_severity_count", 0),
                )
            else:
                self._last_drift_count = 0
            self._last_error = None
            if self._is_clean_for_trading(report):
                self._notify_first_success()
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.error("Reconciliation failed: %s", exc)
            return None
        finally:
            self._run_count += 1
            self._last_run_at = time.monotonic()
            if self._event_bus is not None:
                try:
                    from domain.events.types import DomainEvent

                    # Publish the canonical RECONCILIATION_COMPLETED with
                    # a sub-type indicator so operators watching the bus
                    # see drift/ok without needing a second event type.
                    if self._last_drift_count > 0:
                        payload = {
                            "drift_count": self._last_drift_count,
                            "run_count": self._run_count,
                            "status": "drift",
                        }
                    else:
                        payload = {
                            "drift_count": 0,
                            "run_count": self._run_count,
                            "status": "ok",
                        }
                    self._event_bus.publish(
                        DomainEvent.now(
                            "RECONCILIATION_COMPLETED",
                            payload,
                        )
                    )
                    # G6: emit RECONCILIATION_DRIFT when drift is detected
                    # so the bus-level drift signal is available to monitors,
                    # dashboards, and auto-healing subscribers.
                    if self._last_drift_count > 0:
                        self._event_bus.publish(
                            DomainEvent.now(
                                "RECONCILIATION_DRIFT",
                                {
                                    "drift_count": self._last_drift_count,
                                    "drift_items": [
                                        {
                                            "kind": getattr(d, "kind", "unknown"),
                                            "severity": getattr(d, "severity", "unknown"),
                                            "symbol": getattr(d, "symbol", ""),
                                            "details": getattr(d, "details", ""),
                                        }
                                        for d in getattr(report, "drift_items", [])
                                    ],
                                },
                            )
                        )
                except Exception:
                    logger.exception("Failed to publish RECONCILIATION_COMPLETED")
        return report

    @staticmethod
    def _is_clean_for_trading(report: ReconciliationReport | Any) -> bool:
        """Trading is enabled only after a drift-free reconciliation run."""
        if report is None:
            return False
        if getattr(report, "has_drift", False):
            return False
        if getattr(report, "high_severity_count", 0) > 0:
            return False
        return True

    def _notify_first_success(self) -> None:
        if self._first_success_notified or self._on_first_success is None:
            return
        self._first_success_notified = True
        try:
            self._on_first_success()
        except Exception:
            logger.exception("Reconciliation on_first_success callback failed")
