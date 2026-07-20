"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture.

This module is a **thin orchestrator** that delegates OMS wiring to
:class:`~interface.ui.services.oms_bootstrap.OmsBootstrap` and exposes
:meth:`~BrokerService.build_runtime` as the single composition entry
(ADR-017 → :func:`runtime.factory.build`).

Focused helpers:
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from application.oms.context import TradingContext
from domain import Order, Side
from domain.enums import BrokerId
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from infrastructure.lifecycle.lifecycle import LifecycleManager
from interface.ui.services.broker_registry import (
    create_seeded_mock_broker,
    get_mock_broker_class,
    get_paper_gateway_class,
)

# Concrete broker classes are obtained via the registry (the sole cli module
# permitted to import broker implementations) rather than imported directly,
# to satisfy the CLI broker-implementation isolation contract.
PaperGateway = get_paper_gateway_class()
MockBroker = get_mock_broker_class()

from domain.ports.bootstrap import BootstrapResult, BootstrapStatus
from interface.ui.services.broker_manager import BrokerManager
from interface.ui.services.broker_observability import (
    compute_live_actionable,
)
from interface.ui.services.broker_registry import bootstrap_gateway, resolve_env_path
from interface.ui.services.cli_broker_facade import CliBrokerFacade
from interface.ui.services.market_data_bootstrap import MarketDataBootstrap

# ── Extracted focused classes ────────────────────────────────────────────
from interface.ui.services.oms_bootstrap import OmsBootstrap

logger = logging.getLogger(__name__)


# Legacy — kept for backward compatibility; new code should use
# ``broker_registry.resolve_env_path()``.
_ENV_PATH = Path(__file__).resolve().parents[4] / ".env.local"


# ---------------------------------------------------------------------------
# BrokerService
# ---------------------------------------------------------------------------


class BrokerService:
    """Resolves and manages the active broker (live Dhan gateway or mock).

    Lifecycle ownership
    -------------------
    The service owns a :class:`LifecycleManager` (Phase A / A5) so every
    ``ManagedService`` produced downstream — the ``TokenRefreshScheduler``
    registered by broker factory bootstrap, the ``ReconciliationService``
    attached by ``TradingContext``, and any future scheduler — is drained
    cleanly on ``close()``.

    Previously the ``TokenRefreshScheduler`` was started as a bare daemon
    thread by factory daemon-thread path and never
    stopped; the CLI's ``close()`` only called
    ``TradingContext.stop_reconciliation()`` and ``gateway.close()``. This
    left the scheduler thread to be reaped at process exit. See
    PRODUCTION_CERTIFICATION_REPORT §B4.
    """

    def __init__(
        self,
        *,
        authorize_risk_fail_open: bool = False,
        event_bus: Any | None = None,
    ) -> None:
        """Build the broker service.

        Parameters
        ----------
        authorize_risk_fail_open:
            Explicit operator consent to use the legacy 1,000,000 INR
            placeholder capital when the real broker balance is unavailable.
            This is the **only** path that authorises the override; setting
            ``RISK_FAIL_OPEN=1`` in the environment without this flag is
            refused at startup to prevent silent risk-gate bypasses.
        """
        self._gateway: MarketDataGateway | None = None
        self._upstox_gateway: MarketDataGateway | None = None
        self._paper: PaperGateway | None = None
        self._mock: MockBroker | None = None
        self._active_name: str = BrokerId.DHAN
        self._dhan_load_error: str | None = None
        self._upstox_load_error: str | None = None
        self._dhan_bootstrap: BootstrapResult | None = None
        self._upstox_bootstrap: BootstrapResult | None = None
        self._initialized = False
        self._trading_context: TradingContext | None = None
        self._http_observability = None  # B8+B9 followup
        # B-3 / M-7: explicit fail-open override; default = FAIL CLOSED.
        env_value = os.environ.get("RISK_FAIL_OPEN")
        env_requested = env_value == "1"
        self._risk_fail_open = bool(authorize_risk_fail_open) and (
            env_requested or env_value is None
        )
        if env_requested and not authorize_risk_fail_open:
            logger.error(
                "risk_fail_open_refused",
                extra={
                    "reason": "RISK_FAIL_OPEN=1 set in environment without --risk-fail-open flag",
                    "action": "refusing to use placeholder capital",
                },
            )
            raise RuntimeError(
                "RISK_FAIL_OPEN=1 is set in the environment but the CLI was not "
                "started with --risk-fail-open. Refusing to authorise the legacy "
                "1,000,000 INR placeholder. Either unset the env var or pass "
                "--risk-fail-open explicitly."
            )
        # B-3 / M-7: every capital_fn fallback is recorded in this counter
        self._capital_fallback_count: int = 0
        # A5: every background service is owned by this LifecycleManager.
        self._lifecycle = LifecycleManager()
        # M-7 / Phase 1.2: production readiness gate result.
        self._live_actionable: bool = False
        self._readiness_report: Any = None
        # M4: tracks which broker the OMS submit_fn is wired to.
        # Set when TradingContext is built; used by set_active_broker
        # to prevent cross-broker OMS writes.
        self._oms_broker_id: str | None = None
        if event_bus is None:
            from infrastructure.bootstrap import build_production_event_bus
            from runtime.resilience import ResilienceConfig

            event_bus = build_production_event_bus(resilience=ResilienceConfig.from_env())
        self._event_bus = event_bus
        from infrastructure.event_bus.async_event_bus import AsyncEventBus

        if isinstance(event_bus, AsyncEventBus):
            self._lifecycle.register(event_bus.as_managed_service())

        # ── Compose the focused modules ──────────────────────────────────
        self._oms = OmsBootstrap(self)
        self._facade = CliBrokerFacade(self)
        self._manager = BrokerManager(self)
        self._market_data = MarketDataBootstrap(self)

    # ==================================================================
    # Properties — thin delegation to BrokerManager
    # ==================================================================

    @property
    def lifecycle(self) -> LifecycleManager:
        """The LifecycleManager that owns every background service."""
        return self._lifecycle

    @property
    def http_observability(self):
        """The HTTP observability server (Phase B / B8+B9)."""
        return self._http_observability

    @property
    def trading_context(self) -> TradingContext | None:
        """Return the shared TradingContext (may be *None* before init)."""
        self._ensure_initialized()
        return self._trading_context

    @property
    def active_broker(self) -> MarketDataGateway | PaperGateway | MockBroker:
        """Return the active broker: live Dhan, live Upstox, paper, or mock."""
        return self._manager.get_active_broker()

    @property
    def active_broker_name(self) -> str:
        return self._manager.get_active_broker_name()

    @property
    def gateways(self) -> dict[str, Any]:
        """All bootstrapped broker gateways keyed by ``broker_id``.

        Single seam for the runtime composition root to select brokers by
        id (no private-attr string access). Missing/!loaded brokers are
        simply absent from the dict.
        """
        gw: dict[str, Any] = {}
        if self._gateway is not None:
            gw[BrokerId.DHAN] = self._gateway
        if self._upstox_gateway is not None:
            gw[BrokerId.UPSTOX] = self._upstox_gateway
        if self._paper is not None:
            gw[BrokerId.PAPER] = self._paper
        if self._mock is not None:
            gw["mock"] = self._mock
        return gw

    @property
    def is_live_dhan_active(self) -> bool:
        """``True`` when a real ``BrokerGateway`` is connected (not mock)."""
        return self._manager.is_live_dhan_active()

    @property
    def live_actionable(self) -> bool:
        """``True`` when the runtime is safe to place live orders."""
        return self._manager.is_live_actionable()

    @property
    def readiness_report(self):
        """The most recent :class:`ReadinessReport` from the production
        readiness gate, or ``None`` if init has not run yet."""
        return self._manager.get_readiness_report()

    @property
    def dhan_load_error(self) -> str | None:
        return self._manager.get_dhan_load_error()

    @property
    def dhan_gateway(self) -> MarketDataGateway | None:
        """Public access to the Dhan gateway (G1: replaces getattr(_gateway))."""
        return self._gateway

    @property
    def upstox_gateway(self) -> MarketDataGateway | None:
        """Public access to the Upstox gateway (G1: replaces getattr(_upstox_gateway))."""
        return self._upstox_gateway

    @property
    def http_sessions(self) -> list[Any] | None:
        """Outbound HTTP sessions registered for SSL hardening checks."""
        return getattr(self, "_http_sessions", None)

    @property
    def live_intent(self) -> bool:
        """True if a live broker bootstrap was attempted."""
        return getattr(self, "_live_intent", False)

    @property
    def oms_broker_id(self) -> str | None:
        """The broker ID the OMS submit_fn is wired to."""
        return getattr(self, "_oms_broker_id", None)

    @property
    def allow_live_orders(self) -> bool:
        """Whether the active broker is permitted to place live orders.

        Mirrors the per-broker guard enforced by the leaf order adapters
        (``broker.settings.allow_live_orders``), so the API gate and the
        executor-level gate agree on the same source of truth. Returns
        ``False`` for paper/mock/unknown brokers (fail-closed).
        """
        name = self._manager.get_active_broker_name()
        gw = self.gateways.get(name)
        if gw is None:
            return False
        settings = getattr(gw, "settings", None)
        if settings is None:
            return False
        return bool(getattr(settings, "allow_live_orders", False))

    # ==================================================================
    # Initialization
    # ==================================================================

    def initialize(self) -> None:
        """Eagerly run automatic gateway bootstrap (auth probe included).

        Equivalent to the first property access that needs a live gateway.
        Safe to call multiple times.
        """
        self._ensure_initialized()

    def market_gateway(self, name: str) -> MarketDataGateway:
        """Bootstrap *name* for read-only market data only — no OMS/risk
        manager/reconciliation wiring and no ``ProductionReadinessChecker``
        gate. Independent of :meth:`_ensure_initialized`/the live-trade
        bootstrap, so it never discards a working gateway over an unrelated
        trade-readiness failure, and never requires one to run.
        """
        return self._market_data.market_gateway(name)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        # Broker WebSocket services (e.g. Upstox's asyncio-based market feed)
        # need a live, persistently-pumping event loop before their start()
        # runs via self._lifecycle.start_all() / register() below — otherwise
        # they fall back to an ephemeral loop that's closed the instant
        # connect() returns, silently killing the read loop.
        from runtime.event_loop import ensure_runtime_loop_running

        ensure_runtime_loop_running()
        # Paper always available for diagnostics / sim
        try:
            self._paper = PaperGateway()
        except Exception:
            self._paper = None

        if _ENV_PATH.exists():
            try:
                # B7: OMS risk_manager first (capital gate for live orders).
                oms_risk_manager, oms_capital_provider = self._build_oms_risk_manager()
                self._oms_capital_provider = oms_capital_provider
                # Production path: bootstrap = create + automatic auth probe
                result = bootstrap_gateway(
                    BrokerId.DHAN,
                    env_path=_ENV_PATH,
                    load_instruments=True,
                    lifecycle=self._lifecycle,
                    risk_manager=oms_risk_manager,
                )
                self._dhan_bootstrap = result
                if not result.live_ready:
                    self._dhan_load_error = result.error or result.status.value
                    self._gateway = None
                    self._live_actionable = False
                    logger.warning(
                        "Dhan bootstrap not live-ready: %s (%s)",
                        result.status.value,
                        result.error,
                    )
                else:
                    self._gateway = result.gateway
                    if hasattr(self, "_oms_gateway_holder"):
                        self._oms_gateway_holder["gw"] = self._gateway
                    if oms_capital_provider is not None and hasattr(
                        oms_capital_provider, "update_gateway"
                    ):
                        oms_capital_provider.update_gateway(self._gateway)
                    self._build_and_register_oms_services(oms_risk_manager)
                    self._start_websocket_services()
                    self._lifecycle.start_all()
                    self._start_http_observability_server(oms_risk_manager)
                    from application.services.production_readiness import (
                        ProductionReadinessChecker,
                    )

                    self._readiness_report = ProductionReadinessChecker(self).run_or_raise()
                    self._live_actionable = compute_live_actionable(
                        live_intent=True,
                        gateway=self._gateway,
                        dhan_load_error=self._dhan_load_error,
                        dhan_bootstrap=self._dhan_bootstrap,
                        readiness_report=self._readiness_report,
                    )
                    logger.info(
                        "Dhan bootstrap READY (probe=%s refreshed=%s live_actionable=%s)",
                        result.probe_name,
                        result.refreshed_token,
                        self._live_actionable,
                    )
            except Exception as exc:
                self._dhan_load_error = str(exc)
                self._dhan_bootstrap = BootstrapResult(
                    status=BootstrapStatus.FAILED,
                    broker="dhan",
                    error=str(exc),
                )
                self._gateway = None
                self._live_actionable = False
                logger.warning("Failed to bootstrap Dhan gateway: %s", exc)

        if self._gateway is None:
            # M5: When live bootstrap failed and live intent was detected,
            # fail explicitly — do NOT silently substitute a mock broker.
            if _ENV_PATH.exists():
                self._live_actionable = False
                logger.warning(
                    "Dhan bootstrap failed with live intent — mock broker created for "
                    "diagnostics only. Live orders are BLOCKED (live_actionable=False). "
                    "Run `tradex doctor` to diagnose."
                )
            self._mock = create_seeded_mock_broker(BrokerId.DHAN)

        # Upstox — same automatic auth bootstrap
        upstox_env_path = resolve_env_path(BrokerId.UPSTOX)
        if upstox_env_path is not None and upstox_env_path.exists():
            try:
                result = bootstrap_gateway(
                    BrokerId.UPSTOX,
                    env_path=upstox_env_path,
                    load_instruments=True,
                    lifecycle=self._lifecycle,
                )
                self._upstox_bootstrap = result
                if result.live_ready:
                    self._upstox_gateway = result.gateway
                    logger.info(
                        "Upstox bootstrap READY (probe=%s refreshed=%s)",
                        result.probe_name,
                        result.refreshed_token,
                    )
                else:
                    self._upstox_gateway = None
                    self._upstox_load_error = result.error or result.status.value
                    logger.warning(
                        "Upstox bootstrap not live-ready: %s (%s)",
                        result.status.value,
                        result.error,
                    )
            except Exception as exc:
                self._upstox_load_error = str(exc)
                self._upstox_bootstrap = BootstrapResult(
                    status=BootstrapStatus.FAILED,
                    broker=BrokerId.UPSTOX,
                    error=str(exc),
                )
                self._upstox_gateway = None
                logger.warning("Failed to bootstrap Upstox gateway: %s", exc)

        # Wire the live-actionable gate so the fail-closed production
        # readiness check is live on the order path (not just the bool).
        from runtime.platform_bridge import set_live_actionable_gate

        set_live_actionable_gate(lambda: self._live_actionable)

    # ==================================================================
    # Delegation stubs — backward compat for tests that mock these
    # ==================================================================

    def _build_oms_risk_manager(self):
        return self._oms.build_risk_manager()

    def _build_and_register_oms_services(self, risk_manager) -> None:
        self._oms.build_and_register_services(risk_manager)
        # M4: track which broker the OMS is wired to for cross-broker guard
        self._oms_broker_id = self._active_name

    def _start_websocket_services(self) -> None:
        self._oms.start_websocket_services()

    def _start_http_observability_server(self, risk_manager) -> None:
        self._oms.start_http_observability_server(risk_manager)

    def _oms_orders(self) -> list:
        return self._facade.oms_orders()

    def _oms_trades(self) -> list:
        return self._facade.oms_trades()

    def _ensure_oms_gateway(self):
        return self._facade.ensure_oms_gateway()

    # ==================================================================
    # Public methods — thin delegation to focused modules
    # ==================================================================

    def get_order_stats(self) -> dict[str, int]:
        """Collect order counts by status."""
        return self._facade.get_order_stats()

    def get_orders(self, status_filter: str | None = None) -> list:
        """Fetch orders with optional status filter."""
        return self._facade.get_orders(status_filter)

    def get_trades(self) -> list:
        """Fetch trades for the day."""
        return self._facade.get_trades()

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 0,
        price: Decimal | None = None,
        order_type: str = "MARKET",
    ) -> Order:
        """Place order via CLI facade → ExecutionService → PlaceOrderUseCase → OMS."""
        return self._facade.place_order(
            symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        return self._facade.cancel_order(order_id)

    def set_active_broker(self, name: str) -> None:
        self._manager.set_active_broker(name)

    def use_paper(self) -> None:
        """Switch to paper trading mode."""
        self._manager.use_paper()

    def get_broker_statuses(self) -> list[dict[str, str]]:
        return self._manager.get_broker_statuses()

    # ==================================================================
    # Composition root
    # ==================================================================

    def build_runtime(self, **kwargs: Any) -> Any:
        """Canonical runtime wiring (ADR-017): ``runtime.factory.build`` after init."""
        from runtime.factory import build

        self._ensure_initialized()
        return build(self, **kwargs)

    # ==================================================================
    # Shutdown
    # ==================================================================

    def close(self) -> None:
        """Clean up the live gateway connection and stop every managed service.

        Order matters:
          1. ``lifecycle.stop_all()`` first — drains the
             ``TokenRefreshScheduler`` and ``ReconciliationService`` (and
             any future ``ManagedService``) with bounded timeouts.
          2. ``trading_context.stop_reconciliation()`` — kept for
             backwards compatibility with any context that did not
             receive an attach_lifecycle call (no-op if already drained).
          3. ``gateway.close()`` — closes the HTTP session and any
             broker-owned resources.

        A failure in any step is logged and swallowed so the CLI can
        always exit cleanly.
        """
        # 1. Drain every ManagedService via the LifecycleManager.
        try:
            from runtime.live_datalake_wiring import flush_live_bar_pipeline

            flush_live_bar_pipeline()
        except Exception as exc:
            logger.debug("live_bar_flush_failed: %s", exc)
        try:
            self._lifecycle.stop_all()
        except Exception as exc:
            logger.warning("lifecycle_stop_all_failed: %s", exc)
        # 2. Best-effort belt-and-suspenders for any context that did
        #    not receive the lifecycle. Safe to call twice.
        if self._trading_context is not None:
            try:
                self._trading_context.stop_reconciliation()
            except Exception as exc:
                logger.debug("reconciliation_stop_failed: %s", exc)
            self._trading_context = None
        # 3. Close the live gateway. This closes the HTTP session and
        #    any broker-owned resources.
        if self._gateway is not None:
            try:
                self._gateway.close()
            except Exception as exc:
                logger.debug("gateway_close_failed: %s", exc)
