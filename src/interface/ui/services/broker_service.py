"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture.

This module is now a **thin orchestrator** (~250 lines) that composes three
focused classes:

- :class:`~cli.services.oms_bootstrap.OmsBootstrap` — OMS setup, DI wiring,
  risk manager construction, HTTP observability, WebSocket services.
- :class:`~cli.services.cli_broker_facade.CliBrokerFacade` — Order routing
  for the CLI (place, cancel, get orders/trades).
- :class:`~cli.services.broker_manager.BrokerManager` — Active broker
  switching, status queries, readiness properties.

All business logic lives in the extracted modules; BrokerService owns the
shared mutable state and delegates.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain import Order, Side
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from infrastructure.lifecycle.lifecycle import LifecycleManager
from application.oms.context import TradingContext
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

from interface.ui.services.broker_registry import bootstrap_gateway, create_gateway, resolve_env_path
from domain.errors import BrokerNotReadyError
from domain.ports.bootstrap import BootstrapResult, BootstrapStatus
from interface.ui.services.broker_observability import (
    compute_live_actionable,
    resolve_active_broker,
)

# ── Extracted focused classes ────────────────────────────────────────────
from interface.ui.services.oms_bootstrap import OmsBootstrap
from interface.ui.services.cli_broker_facade import CliBrokerFacade
from interface.ui.services.broker_manager import BrokerManager

logger = logging.getLogger(__name__)


# Legacy — kept for backward compatibility; new code should use
# ``broker_registry.resolve_env_path()``.
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env.local"


# ---------------------------------------------------------------------------
# BrokerService
# ---------------------------------------------------------------------------

class BrokerService:
    """Resolves and manages the active broker (live Dhan gateway or mock).

    Lifecycle ownership
    -------------------
    The service owns a :class:`LifecycleManager` (Phase A / A5) so every
    ``ManagedService`` produced downstream — the ``TokenRefreshScheduler``
    registered by ``BrokerFactory.create``, the ``ReconciliationService``
    attached by ``TradingContext``, and any future scheduler — is drained
    cleanly on ``close()``.

    Previously the ``TokenRefreshScheduler`` was started as a bare daemon
    thread by    ``BrokerFactory().create()``'s daemon-thread path and never
    stopped; the CLI's ``close()`` only called
    ``TradingContext.stop_reconciliation()`` and ``gateway.close()``. This
    left the scheduler thread to be reaped at process exit. See
    PRODUCTION_CERTIFICATION_REPORT §B4.
    """

    def __init__(
        self,
        *,
        authorize_risk_fail_open: bool = False,
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
        self._active_name: str = "dhan"
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

        # ── Compose the three focused modules ──────────────────────────
        self._oms = OmsBootstrap(self)
        self._facade = CliBrokerFacade(self)
        self._manager = BrokerManager(self)

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

    # ==================================================================
    # Initialization
    # ==================================================================

    def initialize(self) -> None:
        """Eagerly run automatic gateway bootstrap (auth probe included).

        Equivalent to the first property access that needs a live gateway.
        Safe to call multiple times.
        """
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        # Paper always available for diagnostics / sim
        try:
            self._paper = PaperGateway()
        except Exception:
            self._paper = None

        if _ENV_PATH.exists():
            try:
                # B7: OMS risk_manager first (capital gate for live orders).
                oms_risk_manager = self._build_oms_risk_manager()
                # Production path: bootstrap = create + automatic auth probe
                result = bootstrap_gateway(
                    "dhan",
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
            self._mock = create_seeded_mock_broker("dhan")

        # Upstox — same automatic auth bootstrap
        upstox_env_path = resolve_env_path("upstox")
        if upstox_env_path is not None and upstox_env_path.exists():
            try:
                result = bootstrap_gateway(
                    "upstox",
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
                    broker="upstox",
                    error=str(exc),
                )
                self._upstox_gateway = None
                logger.warning("Failed to bootstrap Upstox gateway: %s", exc)

    # ==================================================================
    # Delegation stubs — backward compat for tests that mock these
    # ==================================================================

    def _build_oms_risk_manager(self):
        return self._oms.build_risk_manager()

    def _build_and_register_oms_services(self, risk_manager) -> None:
        self._oms.build_and_register_services(risk_manager)

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
            symbol, exchange=exchange, side=side, quantity=quantity,
            price=price, order_type=order_type,
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
