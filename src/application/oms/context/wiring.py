"""Wiring / dependency-injection methods for TradingContext.

Extracted from context.py to reduce god-object size. These methods handle
lifecycle registration and post-construction reconciliation attachment.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from application.oms.lifecycle import (
    register_daily_pnl_reset as _register_daily_pnl_reset_fn,
    register_dlq_monitor as _register_dlq_monitor_fn,
    register_processed_trade_cleanup as _register_processed_trade_cleanup_fn,
)
from application.oms.protocols import IReconciliationService
from application.oms.reconciliation_service import ReconciliationService
from domain.constants import RECONCILIATION_INTERVAL_SECONDS
from domain.events.types import EventType
from domain.ports.lifecycle import LifecycleManagerPort

logger = logging.getLogger(__name__)


class TradingContextWiringMixin:
    """Mixin providing DI / wiring methods for TradingContext."""

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
        _register_processed_trade_cleanup_fn(lifecycle, self._processed_trades)
        _register_dlq_monitor_fn(lifecycle, self._dead_letter_queue)
        _register_daily_pnl_reset_fn(lifecycle, self._risk_manager)

        # Register TradingContext itself as a ManagedService so
        # it participates in deterministic start/stop via the lifecycle.
        lifecycle.register(self)

        if self._orchestrator is not None:
            lifecycle.register(self._orchestrator)
            logger.info("TradingOrchestrator registered with lifecycle")

    def attach_reconciliation_service(
        self,
        reconciliation_service: IReconciliationService,
        *,
        lifecycle: LifecycleManagerPort | None = None,
        reconciliation_interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    ) -> None:
        """Attach a broker reconciliation service to a live TradingContext.

        Mirrors the ``reconciliation_service`` wiring done in ``__init__`` so
        callers (the OMS bootstrap, which must build the broker reconciler
        with ``oms=self.order_manager`` *after* the context exists) can attach
        it post-construction. This is the method the bootstrap actually calls;
        previously it was referenced but never implemented, so reconciliation
        silently never attached on that path (local OMS state never healed
        against broker truth).

        Idempotent: a second call replaces the existing service, unsubscribing
        the prior hot-path requests so events are not double-handled.
        """
        if self._reconciliation_service is not None:
            # ponytail: replace-in-place rather than raise — bootstrap can be
            # re-entered on broker switch; unsubscribe the exact lambda hooks
            # we registered (they capture the wrapper, so they must be stored).
            for _evt, _h in getattr(self, "_recon_handlers", []):
                try:
                    self._event_bus.unsubscribe(_evt, _h)
                except Exception:  # pragma: no cover - defensive
                    pass
            self._order_manager.clear_placement_gate()
            try:
                self._reconciliation_service.stop()
            except Exception:  # pragma: no cover - defensive
                pass

        # I6: lightweight ExecutionEngine for reconciliation heal; mirrors __init__.
        from application.execution.execution_engine import ExecutionEngine
        from application.execution.fill_source import SimulatedFillSource

        self._reconciliation_engine = ExecutionEngine(
            fill_source=SimulatedFillSource(),
            trading_context=self,
        )
        self._reconciliation_service = ReconciliationService(
            order_manager=self._order_manager,
            position_manager=self._position_manager,
            reconciliation_service=reconciliation_service,
            interval_seconds=reconciliation_interval_seconds,
            event_bus=self._event_bus,
            on_first_success=self._mark_reconciliation_ready,
            execution_engine=self._reconciliation_engine,
        )
        self._order_manager.set_placement_gate(self._reconciliation_placement_gate)
        # Mirror __init__: orders stay gated until the first clean reconciliation.
        self._reconciliation_ready = False
        # G6: hot-path reconciliation — wake the loop on order lifecycle events.
        # The bus invokes handlers with the event arg, so wrap the no-arg
        # request_reconciliation (same fix as the __init__ wiring). Store the
        # lambda handles so a re-attach can unsubscribe exactly these.
        _on_trade = lambda *_a: self._reconciliation_service.request_reconciliation()
        _on_order = lambda *_a: self._reconciliation_service.request_reconciliation()
        self._event_bus.subscribe(EventType.TRADE_APPLIED.value, _on_trade)
        self._event_bus.subscribe(EventType.ORDER_UPDATED.value, _on_order)
        self._recon_handlers = [
            (EventType.TRADE_APPLIED.value, _on_trade),
            (EventType.ORDER_UPDATED.value, _on_order),
        ]
        if lifecycle is not None:
            lifecycle.register(self._reconciliation_service)
            if os.getenv("TRADEX_SKIP_STARTUP_RECONCILIATION") != "1":
                self._reconciliation_service.run_now()
