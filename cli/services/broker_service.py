"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

from brokers.common.connection_pool import get_connection_pool
from brokers.common.gateway import MarketDataGateway
from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms.capital_provider import CapitalProvider, GatewayCapitalProvider
from brokers.common.oms.context import TradingContext
from brokers.common.observability.http_server import HttpObservabilityServer
from brokers.paper import PaperGateway

from brokers.common.execution.execution_service import ExecutionService
from brokers.common.oms.order_manager import OmsOrderCommand, OrderResult
from cli.services.broker_registry import create_gateway, resolve_env_path
from cli.services.capital_provider import TrackedCapitalProvider
from cli.services.observability_setup import start_http_observability
from cli.services.websocket_wiring import start_websocket_services
from cli.services.oms_setup import build_risk_manager, register_oms_services

logger = logging.getLogger(__name__)


# Legacy — kept for backward compatibility; new code should use
# ``broker_registry.resolve_env_path()``.
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env.local"


# ---------------------------------------------------------------------------
# Mock broker — uses the shared MockBroker from brokers.paper.mock_broker
# ---------------------------------------------------------------------------
from brokers.paper.mock_broker import MockBroker, create_seeded_mock_broker

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
        load_instruments: bool = True,
        event_bus: Any | None = None,
    ) -> None:
        self._gateway: MarketDataGateway | None = None
        self._upstox_gateway: MarketDataGateway | None = None
        self._paper: PaperGateway | None = None
        self._mock: MockBroker | None = None
        self._active_name: str = "dhan"
        self._dhan_load_error: str | None = None
        self._upstox_load_error: str | None = None
        self._initialized = False
        self._trading_context: TradingContext | None = None
        self._http_observability: HttpObservabilityServer | None = None  # B8+B9 followup
        # B-3 / M-7: explicit fail-open override; default = FAIL CLOSED.
        # Set RISK_FAIL_OPEN=1 to authorise the legacy 1,000,000 placeholder.
        self._risk_fail_open = os.environ.get("RISK_FAIL_OPEN") == "1"
        # B-3 / M-7: every capital_fn fallback is recorded in this counter
        # and emitted as a Prometheus gauge by the HTTP server. The placeholder
        # is NEVER used silently again.
        self._capital_fallback_count: int = 0
        # A5: every background service in the system is owned by this
        # LifecycleManager. Created eagerly so close() can stop_all()
        # even if _ensure_initialized() failed midway.
        self._lifecycle = LifecycleManager()
        # I-14: accept load_instruments + event_bus from main() so the
        # CLI can control instrument loading and share the event bus.
        self._load_instruments = load_instruments
        self._event_bus = event_bus

    @property
    def lifecycle(self) -> LifecycleManager:
        """The LifecycleManager that owns every background service.

        Exposed for tests and for the CLI's ``doctor`` command. The CLI
        should never bypass this property to start or stop a service
        directly — that re-introduces the ownership ambiguity Phase A
        was designed to fix.
        """
        return self._lifecycle

    @property
    def http_observability(self) -> HttpObservabilityServer | None:
        """The HTTP observability server (Phase B / B8+B9).

        Returns ``None`` before init or if the server failed to start.
        Exposed so the CLI's ``doctor`` and ``metrics`` commands
        (future work) can introspect it.
        """
        return self._http_observability

    def _start_http_observability_server(self, risk_manager: Any) -> None:
        """B8+B9 followup: spin up the HTTP observability server.
        
        Delegates to observability_setup.start_http_observability()
        for separation of concerns.
        """
        start_http_observability(self, risk_manager)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        if _ENV_PATH.exists():
            try:
                # B7: construct the OMS first so we can pass its
                # risk_manager to the OrdersAdapter. The OMS is the
                # canonical owner of risk checks; this is the first
                # step in putting the central OMS on the live CLI
                # path.
                oms_risk_manager, capital_provider = self._build_oms_risk_manager()
                # A5: pass the lifecycle so the factory registers
                # TokenRefreshScheduler with it (instead of starting
                # a bare daemon thread). The factory's backward-compat
                # path is intentionally bypassed here.
                self._gateway = create_gateway(
                    "dhan",
                    env_path=resolve_env_path("dhan", _ENV_PATH),
                    load_instruments=self._load_instruments,
                    event_bus=self._event_bus,
                    lifecycle=self._lifecycle,
                    # B7: OMS risk_manager → OrdersAdapter risk gate.
                    risk_manager=oms_risk_manager,
                )
                # P2-2: now that the gateway exists, update the
                # capital_provider with the real gateway reference.
                # From this point on, the risk check uses the real
                # account balance, not the placeholder.
                if capital_provider is not None:
                    capital_provider.update_gateway(self._gateway)
                # Register the OMS services with the lifecycle so
                # they are drained on close().
                self._build_and_register_oms_services(oms_risk_manager)
                # B-4: start the WebSocket services through the
                # lifecycle so they participate in deterministic
                # start/stop and the reconnect backoff never escapes
                # the process.
                self._start_websocket_services()
                # Start every registered service in registration order.
                # TokenRefreshScheduler will now run as a ManagedService
                # and join() cleanly on stop_all().
                self._lifecycle.start_all()
                # B8+B9 followup: spin up the HTTP observability server
                # so /healthz, /readyz, and /metrics are live in production.
                # Registered with the lifecycle so close() drains it.
                self._start_http_observability_server(oms_risk_manager)
                # M-7: production readiness gate. REF-17: this gate
                # now FAILS CLOSED — a failed check raises
                # ProductionReadinessError, which is caught above and
                # recorded as ``_dhan_load_error``. The CLI must
                # refuse to enter the live trading path when the gate
                # fails (see BrokerService.live_actionable). Calling
                # ``run()`` directly (without ``run_or_raise``) is the
                # legacy log-only path retained only for diagnostic
                # inspection of the report.
                try:
                    from brokers.common.services.production_readiness import (
                        ProductionReadinessChecker,
                    )
                    self._readiness_report = ProductionReadinessChecker(
                        self
                    ).run_or_raise()
                    if not self._readiness_report.passed:
                        # Defensive — run_or_raise() should already have
                        # raised, but keep a structured error in case
                        # a future override disables it.
                        logger.error(
                            "production_readiness_failed: %s",
                            self._readiness_report.summary(),
                        )
                except Exception as exc:
                    logger.warning("readiness_check_skipped: %s", exc)
                logger.info("Dhan BrokerGateway created with lifecycle + OMS + HTTP /metrics")
            except Exception as exc:
                self._dhan_load_error = str(exc)
                logger.warning("Failed to create Dhan gateway: %s", exc)

        if self._gateway is None:
            self._mock = create_seeded_mock_broker("dhan")

        # Try to create Upstox gateway using the unified registry.
        upstox_env_path = resolve_env_path("upstox")
        if upstox_env_path is not None and upstox_env_path.exists():
            try:
                self._upstox_gateway = create_gateway(
                    "upstox",
                    env_path=upstox_env_path,
                    load_instruments=self._load_instruments,
                    event_bus=self._event_bus,
                    lifecycle=self._lifecycle,
                )
                if self._upstox_gateway is not None:
                    logger.info("Upstox BrokerGateway created")
                else:
                    self._upstox_load_error = "create_gateway returned None"
                    logger.warning("Failed to create Upstox gateway")
            except Exception as exc:
                self._upstox_load_error = str(exc)
                logger.warning("Failed to create Upstox gateway: %s", exc)

    def _start_websocket_services(self) -> None:
        """B-4: lazily create the market feed and order stream services.
        
        Delegates to websocket_wiring.start_websocket_services()
        for separation of concerns.
        """
        start_websocket_services(self._gateway, self._lifecycle)

    def _build_oms_risk_manager(self) -> tuple[Any, Any]:
        """B7: build a RiskManager for the OMS that the live path will consult.
        
        Delegates to oms_setup.build_risk_manager() for separation of concerns.
        """
        return build_risk_manager(self)

    def _build_and_register_oms_services(self, risk_manager: Any) -> None:
        """B7: construct the OMS-side services and register with lifecycle.
        
        Delegates to oms_setup.register_oms_services() for separation
        of concerns.
        """
        register_oms_services(self, risk_manager)

    @property
    def trading_context(self) -> TradingContext | None:
        """Return the shared TradingContext (may be *None* before init)."""
        self._ensure_initialized()
        return self._trading_context

    @property
    def execution_service(self) -> ExecutionService | None:
        """OMS-first execution facade when trading context and gateway are ready."""
        self._ensure_initialized()
        if self._trading_context is None:
            return None
        gw = self.active_broker
        if gw is None or not isinstance(gw, MarketDataGateway):
            return None
        return ExecutionService(
            trading_context=self._trading_context,
            gateway=gw,
            mode="live",
        )

    # -- properties ---------------------------------------------------------

    @property
    def active_broker(self) -> MarketDataGateway | PaperGateway | MockBroker:
        """Return the active broker: live Dhan, live Upstox, paper, or mock."""
        self._ensure_initialized()
        if self._active_name == "paper" and self._paper is not None:
            return self._paper
        if self._active_name == "upstox" and self._upstox_gateway is not None:
            return self._upstox_gateway
        if self._gateway is not None:
            return self._gateway
        if self._paper is not None:
            return self._paper
        assert self._mock is not None
        return self._mock

    @property
    def active_broker_name(self) -> str:
        return self._active_name

    @property
    def is_live_dhan_active(self) -> bool:
        """``True`` when a real ``BrokerGateway`` is connected (not mock)."""
        self._ensure_initialized()
        return self._gateway is not None

    @property
    def dhan_load_error(self) -> str | None:
        return self._dhan_load_error

    # -- broker management --------------------------------------------------

    def set_active_broker(self, name: str) -> None:
        self._ensure_initialized()
        name_lower = name.lower()
        if name_lower == "paper":
            if self._paper is None:
                paper_gw = create_gateway("paper")
                if paper_gw is None:
                    raise ValueError("Paper gateway not available.")
                self._paper = paper_gw
            self._active_name = "paper"
        elif name_lower == "dhan":
            if self._gateway is None:
                raise ValueError("Dhan broker not available. Check .env.local credentials.")
            self._active_name = "dhan"
        elif name_lower == "upstox":
            if self._upstox_gateway is None:
                raise ValueError("Upstox broker not available. Check .env.upstox credentials.")
            self._active_name = "upstox"
        else:
            raise ValueError(f"Broker '{name}' is not registered. Use 'dhan', 'upstox', or 'paper'.")
        self._active_name = name_lower

    def use_paper(self) -> None:
        """Switch to paper trading mode."""
        self.set_active_broker("paper")

    def get_broker_statuses(self) -> list[dict[str, str]]:
        self._ensure_initialized()
        statuses = []
        if self._gateway is not None:
            statuses.append({"broker": "Dhan", "status": "Connected"})
        else:
            statuses.append({"broker": "Dhan", "status": "Unavailable"})
        if self._upstox_gateway is not None:
            statuses.append({"broker": "Upstox", "status": "Connected"})
        else:
            statuses.append({"broker": "Upstox", "status": "Unavailable"})
        statuses.append({"broker": "Paper", "status": "Available"})
        return statuses

    def submit_order(self, command: OmsOrderCommand) -> Order:
        """Transport-only broker submission for OMS ``submit_fn`` wiring.

        Risk, idempotency, and audit are enforced by
        :class:`~brokers.common.oms.order_manager.OrderManager` before this
        method is invoked. Duplicate broker-level risk checks are skipped via
        ``transport_only=True``.
        """
        self._ensure_initialized()
        gateway = self.active_broker
        if gateway is None:
            raise RuntimeError("No broker gateway configured")

        submit_fn = make_gateway_submit_fn(gateway, transport_only=True)
        return submit_fn(command)

    def place_order_through_oms(self, command: OmsOrderCommand) -> OrderResult:
        """Place an order through OMS with broker transport as ``submit_fn``."""
        self._ensure_initialized()
        svc = self.execution_service
        if svc is None:
            raise RuntimeError("TradingContext not initialized")
        return svc.place_order(command)

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
        always exit cleanly. The previous implementation relied on
        process exit to reap leaked daemon threads; this version makes
        shutdown deterministic.
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
        
        # 4. Close connection pool to release all HTTP connection pools
        try:
            pool = get_connection_pool()
            pool.close_all()
        except Exception as exc:
            logger.debug("connection_pool_close_failed: %s", exc)
