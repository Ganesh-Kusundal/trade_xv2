"""Trading context — wires EventBus, OMS, Position and Risk managers.

Re-exports from sub-modules maintain backward compatibility for all
``from application.oms.context import TradingContext`` imports.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from application.oms.context._types import CancellationResult  # noqa: F401
from application.oms.context.lifecycle import TradingContextLifecycleMixin
from application.oms.context.wiring import TradingContextWiringMixin
from application.oms.event_log_replay import EventLogReplayService
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.shutdown_coordinator import ShutdownCoordinator
from application.oms.protocols import IReconciliationService
from application.oms.reconciliation_service import ReconciliationService
from application.oms._internal.risk_manager import RiskConfig, RiskManager
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

logger = logging.getLogger(__name__)


def _as_decimal(value: object) -> Decimal:
    """Coerce Money/Quantity/scalars to Decimal for equity math."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    amount = getattr(value, "amount", None)
    if amount is not None:
        return Decimal(str(amount))
    magnitude = getattr(value, "magnitude", None)
    if magnitude is not None:
        return Decimal(str(magnitude))
    return Decimal(str(value))


class TradingContext(TradingContextLifecycleMixin, TradingContextWiringMixin):
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
        orchestrator: Any | None = None,
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
            and self._event_bus.event_log is None
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

        # F5: feed session equity delta (current − session-open) into the risk
        # engine so daily-loss is not absolute MTM. Baseline is re-frozen after
        # event-log replay (below) so overnight book is the open, not a loss.
        # Analytics PARITY (ReplayEngine / PaperTradingEngine) sets
        # ``set_analytics_daily_pnl_owner(True)`` so this bus feed is muted and
        # the session bar feed is the sole writer.
        self._analytics_owns_daily_pnl = False
        self._session_open_equity = self._compute_equity()
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
        self._recon_handlers: list[tuple[str, Callable[[Any], None]]] = []
        self._reconciliation_ready = reconciliation_service is None
        if reconciliation_service is not None and reconciliation_interval_seconds > 0:
            # I6: Create a lightweight ExecutionEngine for reconciliation heal.
            # apply_mass_status() only touches OrderManager/PositionManager,
            # never the FillSource, so a SimulatedFillSource is safe here.
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
            # G6: hot-path reconciliation — wake the reconciliation loop on
            # order lifecycle events so drift is detected immediately rather
            # than waiting for the next timer tick. The bus invokes handlers
            # with the event arg, so wrap the no-arg request_reconciliation.
            _on_trade = lambda *_a: self._reconciliation_service.request_reconciliation()
            _on_order = lambda *_a: self._reconciliation_service.request_reconciliation()
            self._event_bus.subscribe(EventType.TRADE_APPLIED.value, _on_trade)
            self._event_bus.subscribe(EventType.ORDER_UPDATED.value, _on_order)
            self._recon_handlers = [
                (EventType.TRADE_APPLIED.value, _on_trade),
                (EventType.ORDER_UPDATED.value, _on_order),
            ]

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

        # F5: freeze session-open equity after replay; clear any feed noise from
        # rebuild so daily-loss measures only post-open moves.
        self._session_open_equity = self._compute_equity()
        if self._risk_manager is not None:
            self._risk_manager.reset_daily_pnl()

        self._orchestrator: Any | None = orchestrator

        # Shutdown thread-safety: _shutdown_lock prevents concurrent shutdown
        # attempts from both passing the guard simultaneously (TD-12).
        self._shutdown_lock = threading.Lock()
        self._shutdown_in_progress = False

    # ── Properties ──────────────────────────────────────────────────────

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

    def health(self) -> dict[str, Any]:
        """Snapshot of observability state for the SRE / alerting layer."""
        order_store = self._order_manager.order_store if hasattr(self._order_manager, 'order_store') else None
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

    def _compute_equity(self) -> Decimal:
        """Session equity proxy: capital + book PnL (realized + unrealized).

        Fixed capital providers keep capital constant so the session delta is
        driven by the book; broker-funds providers already mark cash — book PnL
        still moves with open MTM. Daily-loss uses the delta from
        ``_session_open_equity``, not this absolute level.
        """
        book = Decimal("0")
        for p in self._position_manager.get_positions():
            realized = getattr(p, "realized_pnl", Decimal("0")) or Decimal("0")
            unrealized = getattr(p, "unrealized_pnl", Decimal("0")) or Decimal("0")
            book += _as_decimal(realized) + _as_decimal(unrealized)
        capital = Decimal("0")
        if self._risk_manager is not None:
            try:
                capital = _as_decimal(
                    self._risk_manager.capital_provider.get_available_balance()
                )
            except Exception:
                capital = Decimal("0")
        return capital + book

    def set_analytics_daily_pnl_owner(self, owned: bool) -> None:
        """When True, mute bus ``_feed_daily_pnl`` (analytics session owns daily_pnl)."""
        self._analytics_owns_daily_pnl = bool(owned)

    @contextmanager
    def analytics_parity_scope(self, capital_provider):
        """Scope PARITY risk bindings to a single run and restore on exit.

        Analytics engines (ReplayEngine / PaperTradingEngine) call this from
        ``run()`` so the risk capital binding and daily-pnl ownership flag are
        reverted when the run ends. Without this, a TradingContext reused for
        live trading after a replay would carry replay's capital provider and a
        permanently-muted daily-pnl bus feed.

        No-op (immediately yields) when ``capital_provider`` is None or the
        context has no ``risk_manager`` (PURE_SIM / OMS-less harness).
        """
        if capital_provider is None:
            yield
            return
        risk = self._risk_manager
        if risk is None or not hasattr(risk, "bind_capital_provider"):
            yield
            return
        prev_owner = self._analytics_owns_daily_pnl
        prev_cap = risk.capital_provider
        risk.bind_capital_provider(capital_provider)
        self.set_analytics_daily_pnl_owner(True)
        try:
            yield
        finally:
            self.set_analytics_daily_pnl_owner(prev_owner)
            risk.bind_capital_provider(prev_cap)

    def _feed_daily_pnl(self, event: DomainEvent | None = None) -> None:
        """Push session equity delta into the risk engine (F5).

        Daily-loss = ``current_equity − session_open_equity``, not absolute
        book MTM. Called on every ``POSITION_UPDATED`` / ``POSITION_CLOSED``.
        The tracker stores this session delta and records incremental changes
        for the loss circuit breaker.

        Skipped when analytics PARITY owns the feed via
        :meth:`set_analytics_daily_pnl_owner`.
        """
        if self._analytics_owns_daily_pnl:
            return
        if self._risk_manager is None:
            return
        try:
            session_delta = _as_decimal(self._compute_equity()) - _as_decimal(
                self._session_open_equity
            )
            self._risk_manager.update_daily_pnl(session_delta)
        except Exception:  # pragma: no cover - defensive: never block the bus
            logger.exception("daily_pnl_feed_failed")

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


__all__ = [
    "CancellationResult",
    "TradingContext",
]
