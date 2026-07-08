"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture.

BrokerService is a thin facade that orchestrates three focused modules:

- :mod:`broker_lifecycle` — infrastructure bootstrap, gateway shutdown, mock creation
- :mod:`broker_observability` — health reporting, status collection, active broker resolution
- :mod:`oms_setup` — OMS risk manager and service registration
- :mod:`observability_setup` — HTTP observability server startup
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from application.execution.execution_service import ExecutionService
from application.execution.gateway_submit import make_gateway_submit_fn
from application.oms.context import TradingContext
from application.oms.oms_gateway_proxy import OMSGatewayProxy
from application.oms.order_manager import OmsOrderCommand, OrderResult
from brokers.common.gateway import MarketDataGateway  # sanctioned — broker wiring layer (type annotation)
from cli.services.broker_lifecycle import (
    build_broker_infrastructure,
    close_all_gateways,
    maybe_create_mock_broker,
)
from cli.services.broker_observability import (
    collect_broker_statuses,
    compute_live_actionable,
    compute_upstox_authenticated,
    resolve_active_broker,
)
from cli.services.broker_registry import bootstrap_gateway, create_gateway, resolve_env_path
from cli.services.observability_setup import start_http_observability
from cli.services.oms_setup import build_risk_manager, register_oms_services
from domain.entities import Order
from infrastructure.lifecycle import LifecycleManager

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
        load_instruments: bool = True,
        event_bus: Any | None = None,
        readonly: bool = False,  # NEW: skip TradingContext for read-only commands
    ) -> None:
        # Gateway state
        self._gateway: MarketDataGateway | None = None
        self._upstox_gateway: MarketDataGateway | None = None
        self._paper: Any | None = None
        self._mock: Any | None = None
        self._active_name: str = "dhan"
        self._dhan_load_error: str | None = None
        self._upstox_load_error: str | None = None
        self._initialized = False
        # OMS state
        self._trading_context: TradingContext | None = None
        self._oms_proxy: OMSGatewayProxy | None = None
        self._upstox_oms_proxy: OMSGatewayProxy | None = None
        self._oms_risk_manager: Any = None
        # Risk policy (B-3 / M-7)
        self._risk_fail_open = os.environ.get("RISK_FAIL_OPEN") == "1"
        self._capital_fallback_count: int = 0
        # Lifecycle & infrastructure
        self._lifecycle = LifecycleManager()
        self._broker_infra: Any | None = None
        # Observability
        self._http_observability: Any | None = None
        self._readiness_report: Any = None
        # CLI control flags
        self._load_instruments = load_instruments
        self._event_bus = event_bus
        self._readonly = readonly
        # Bootstrap results
        self._live_intent = False
        self._dhan_bootstrap: Any = None
        self._upstox_bootstrap: Any = None

    # -- lifecycle properties -----------------------------------------------

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
    def http_observability(self) -> Any | None:
        """The HTTP observability server (Phase B / B8+B9).

        Returns ``None`` before init or if the server failed to start.
        Exposed so the CLI's ``doctor`` and ``metrics`` commands
        (future work) can introspect it.
        """
        return self._http_observability

    # -- initialization -----------------------------------------------------

    def initialize(self) -> None:
        """Public initialization entry point (delegates to ``_ensure_initialized``)."""
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Initialise Dhan gateway (or fall back to mock).
        self._ensure_dhan_initialized()

        # Initialise Upstox gateway (best-effort, non-blocking).
        self._ensure_upstox_initialized()

        # Build federated broker infrastructure from available gateways.
        self._ensure_broker_infrastructure()

    def _ensure_dhan_initialized(self) -> None:
        """Create and wire the Dhan gateway.

        When ``.env.local`` exists the live path is attempted.  On failure
        ``_dhan_load_error`` is set and **no mock broker** is substituted —
        live trading must fail closed (see :attr:`live_actionable`).
        """
        if not _ENV_PATH.exists():
            # No live credentials — create mock broker for offline mode.
            self._mock = maybe_create_mock_broker("dhan")
            return

        self._live_intent = True
        oms_risk_manager, capital_provider = self._build_oms_risk_manager()
        self._oms_risk_manager = oms_risk_manager

        try:
            bootstrap = bootstrap_gateway(
                "dhan",
                env_path=resolve_env_path("dhan", _ENV_PATH),
                load_instruments=self._load_instruments,
                event_bus=self._event_bus,
                lifecycle=self._lifecycle,
                risk_manager=oms_risk_manager,
                require_authenticated=True,
            )
            self._dhan_bootstrap = bootstrap
            if not bootstrap.live_ready:
                raise RuntimeError(
                    bootstrap.error
                    or f"Dhan bootstrap status={bootstrap.status.value} "
                    f"(authenticated={bootstrap.authenticated})"
                )
            self._gateway = bootstrap.gateway

            # Readonly mode: gateway exists but no OMS/TradingContext.
            if self._readonly:
                logger.debug("readonly_mode: skipping TradingContext initialization")
                return

            # Wire OMS proxy and register OMS services.
            self._wire_dhan_oms(capital_provider, oms_risk_manager)

            # Run production readiness check and start services.
            if not self._check_readiness_and_start(oms_risk_manager):
                return

            logger.info("Dhan BrokerGateway created with lifecycle + OMS + HTTP /metrics")

        except Exception as exc:
            self._lifecycle.stop_all()
            self._dhan_load_error = str(exc)
            self._gateway = None
            self._oms_proxy = None
            logger.warning("Failed to create Dhan gateway: %s", exc)

    def _wire_dhan_oms(self, capital_provider: Any, oms_risk_manager: Any) -> None:
        """Wire OMS components after successful Dhan gateway creation.

        Updates the capital provider with the real gateway reference,
        creates the OMS enforcement proxy, and registers OMS services
        with the lifecycle.
        """
        # P2-2: Update capital_provider with real gateway reference.
        # From this point on, risk checks use real account balance.
        if capital_provider is not None:
            capital_provider.update_gateway(self._gateway)
        # B4: Create OMS enforcement proxy.
        self._create_dhan_oms_proxy(oms_risk_manager)
        # Register OMS services with lifecycle for clean shutdown.
        self._build_and_register_oms_services(oms_risk_manager)

    def _create_dhan_oms_proxy(self, risk_manager: Any) -> None:
        """B4: Wrap the Dhan gateway with OMS enforcement proxy.

        All order operations check kill switch before reaching the broker.
        Market data operations pass through unchanged.
        """
        self._oms_proxy = OMSGatewayProxy(
            real_gateway=self._gateway,
            risk_manager=risk_manager,
            strict_mode=True,
        )
        logger.info("B4: OMS gateway proxy created — order operations enforced")

    def _check_readiness_and_start(self, oms_risk_manager: Any) -> bool:
        """Run production readiness check and start all services.

        Returns True if services started successfully, False if
        readiness check failed (cleanup already performed).
        """
        # B8+B9: Start HTTP observability server BEFORE readiness check.
        # This ensures the http_observability_started check passes.
        self._start_http_observability_server(oms_risk_manager)

        # P-1.5: Run production readiness check BEFORE starting other services.
        try:
            from brokers.common.services.production_readiness import (  # sanctioned — broker wiring layer
                ProductionReadinessChecker,
                ProductionReadinessError,
            )

            self._readiness_report = ProductionReadinessChecker(self).run_or_raise()
        except ProductionReadinessError as exc:
            self._dhan_load_error = str(exc)
            self._gateway = None
            self._oms_proxy = None
            self._oms_risk_manager = None
            logger.error("production_readiness_failed: %s", exc)
            return False

        # P-1.5: ONLY NOW start remaining services — readiness check passed.
        self._lifecycle.start_all()
        return True

    def _ensure_upstox_initialized(self) -> None:
        """Attempt to create the Upstox gateway (best-effort, non-blocking).

        Failure populates ``self._upstox_load_error`` but never raises;
        the CLI can still operate with Dhan + Paper.
        """
        upstox_env_path = resolve_env_path("upstox")
        if upstox_env_path is None or not upstox_env_path.exists():
            return
        try:
            bootstrap = bootstrap_gateway(
                "upstox",
                env_path=upstox_env_path,
                load_instruments=self._load_instruments,
                event_bus=self._event_bus,
                lifecycle=self._lifecycle,
                require_authenticated=True,
            )
            self._upstox_bootstrap = bootstrap
            if bootstrap.live_ready:
                self._upstox_gateway = bootstrap.gateway
                self._create_upstox_oms_proxy()
                logger.info(
                    "Upstox BrokerGateway created (probe=%s refreshed=%s)",
                    bootstrap.probe_name,
                    bootstrap.refreshed_token,
                )
            else:
                self._upstox_load_error = bootstrap.error or bootstrap.status.value
                logger.warning("Failed to create Upstox gateway: %s", self._upstox_load_error)
        except Exception as exc:
            self._upstox_load_error = str(exc)
            logger.warning("Failed to create Upstox gateway: %s", exc)

    def _create_upstox_oms_proxy(self) -> None:
        """Create OMS enforcement proxy for Upstox gateway."""
        rm = self._oms_risk_manager
        if rm is None:
            rm, _ = self._build_oms_risk_manager()
            self._oms_risk_manager = rm
        self._upstox_oms_proxy = OMSGatewayProxy(
            real_gateway=self._upstox_gateway,
            risk_manager=rm,
            strict_mode=True,
        )

    def _ensure_broker_infrastructure(self) -> None:
        """Bootstrap BrokerInfrastructure from live legacy gateways."""
        if self._broker_infra is not None:
            return
        self._broker_infra = build_broker_infrastructure(
            self._gateway, self._upstox_gateway, self._paper,
        )

    @property
    def broker_infrastructure(self) -> Any | None:
        """Federated routing, quota, historical, and stream infrastructure."""
        self._ensure_initialized()
        if self._broker_infra is None:
            self._ensure_broker_infrastructure()
        return self._broker_infra

    def _start_http_observability_server(self, risk_manager: Any) -> None:
        """B8+B9 followup: spin up the HTTP observability server.

        Delegates to observability_setup.start_http_observability()
        for separation of concerns.
        """
        start_http_observability(self, risk_manager)

    # -- OMS delegation (monkeypatch targets for tests) ---------------------

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

    # -- public properties --------------------------------------------------

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
        if gw is None:
            return None
        # B4: Accept both raw MarketDataGateway and OMSGatewayProxy
        if not isinstance(gw, MarketDataGateway | OMSGatewayProxy):
            return None
        return ExecutionService(
            trading_context=self._trading_context,
            gateway=gw,
            mode="live",
        )

    @property
    def active_broker(self) -> Any:
        """Return the active broker: live Dhan, live Upstox, paper, or mock.

        B4: When a live gateway is active and the OMS proxy has been
        created, the proxy is returned instead of the raw gateway.
        This ensures ALL order operations check the kill switch before
        reaching the broker. Market data operations pass through the
        proxy unchanged.
        """
        self._ensure_initialized()
        return resolve_active_broker(
            self._active_name,
            paper=self._paper,
            oms_proxy=self._oms_proxy,
            gateway=self._gateway,
            upstox_oms_proxy=self._upstox_oms_proxy,
            upstox_gateway=self._upstox_gateway,
            mock=self._mock,
            dhan_load_error=self._dhan_load_error,
            upstox_load_error=self._upstox_load_error,
            dhan_bootstrap=self._dhan_bootstrap,
            upstox_bootstrap=self._upstox_bootstrap,
        )

    @property
    def active_broker_name(self) -> str:
        return self._active_name

    @property
    def active_gateway(self) -> MarketDataGateway | None:
        """Return the active MarketDataGateway for market data streaming."""
        self._ensure_initialized()
        if self._active_name == "upstox":
            return self._upstox_gateway
        return self._gateway

    @property
    def oms_proxy(self) -> OMSGatewayProxy | None:
        """B4: The OMS gateway proxy (enforces kill switch on order ops).

        Returns None when using paper/mock mode or before initialization.
        Tests and internal code can use this to verify enforcement state.
        """
        return self._oms_proxy

    @property
    def upstox_oms_proxy(self) -> OMSGatewayProxy | None:
        """OMS gateway proxy for Upstox (kill switch on order ops)."""
        return self._upstox_oms_proxy

    @property
    def live_actionable(self) -> bool:
        """``True`` when live Dhan gateway passed authenticated readiness."""
        self._ensure_initialized()
        return compute_live_actionable(
            self._live_intent,
            self._gateway,
            self._dhan_load_error,
            self._dhan_bootstrap,
            self._readiness_report,
        )

    @property
    def upstox_authenticated(self) -> bool:
        """``True`` when Upstox passed authenticated readiness probe."""
        self._ensure_initialized()
        return compute_upstox_authenticated(self._upstox_bootstrap)

    @property
    def is_live_dhan_live(self) -> bool:
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
            self._ensure_broker_infrastructure()
        elif name_lower == "dhan":
            if self._gateway is None:
                raise ValueError("Dhan broker not available. Check .env.local credentials.")
            self._active_name = "dhan"
        elif name_lower == "upstox":
            if self._upstox_gateway is None:
                raise ValueError(
                    "Upstox broker not available. Check .env.upstox or .env.local credentials."
                )
            self._active_name = "upstox"
        else:
            raise ValueError(
                f"Broker '{name}' is not registered. Use 'dhan', 'upstox', or 'paper'."
            )
        self._active_name = name_lower

    def use_paper(self) -> None:
        """Switch to paper trading mode."""
        self.set_active_broker("paper")

    def get_broker_statuses(self) -> list[dict[str, str]]:
        """Collect connectivity status for all known brokers."""
        self._ensure_initialized()
        return collect_broker_statuses(self._gateway, self._upstox_gateway)

    # -- order submission ---------------------------------------------------

    def submit_order(self, command: OmsOrderCommand) -> Order:
        """Transport-only broker submission for OMS ``submit_fn`` wiring.

        Risk, idempotency, and audit are enforced by
        :class:`~brokers.common.oms.order_manager.OrderManager` before this
        method is invoked. Duplicate broker-level event publishing is suppressed
        via the ``oms_managed()`` context manager in ``make_gateway_submit_fn``.
        """
        self._ensure_initialized()
        gateway = self.active_broker
        if gateway is None:
            raise RuntimeError("No broker gateway configured")

        fn = make_gateway_submit_fn(gateway)
        return fn(command)

    def place_order_through_oms(self, command: OmsOrderCommand) -> OrderResult:
        """Place an order through OMS with broker transport as ``submit_fn``."""
        self._ensure_initialized()
        svc = self.execution_service
        if svc is None:
            raise RuntimeError("TradingContext not initialized")
        return svc.place_order(command)

    # -- shutdown -----------------------------------------------------------

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
        # 3. Close broker infra, gateways, and connection pool.
        close_all_gateways(self._broker_infra, self._gateway, self._upstox_gateway)
        self._broker_infra = None
        self._gateway = None
        self._upstox_gateway = None
        self._upstox_oms_proxy = None


class BrokerServiceTestBuilder:
    """Explicit test double factory for BrokerService.

    Replaces the fragile ``create_test_double`` classmethod.  Tests declare
    exactly which fields they need, making dependencies visible and
    eliminating silent breakage when new private fields are added.
    """

    def __init__(self) -> None:
        self._gateway: MarketDataGateway | None = None
        self._upstox_gateway: MarketDataGateway | None = None
        self._paper: Any | None = None
        self._mock: Any | None = None
        self._active_name: str = "dhan"
        self._dhan_load_error: str | None = None
        self._upstox_load_error: str | None = None
        self._initialized: bool = True
        self._trading_context: TradingContext | None = None
        self._oms_proxy: OMSGatewayProxy | None = None
        self._upstox_oms_proxy: OMSGatewayProxy | None = None
        self._oms_risk_manager: Any = None
        self._risk_fail_open: bool = False
        self._capital_fallback_count: int = 0
        self._lifecycle = LifecycleManager()
        self._broker_infra: Any | None = None
        self._http_observability: Any | None = None
        self._readiness_report: Any | None = None
        self._load_instruments: bool = False
        self._event_bus: Any | None = None
        self._readonly: bool = False
        self._live_intent: bool = False
        self._dhan_bootstrap: Any = None
        self._upstox_bootstrap: Any = None

    def with_gateway(self, gateway: MarketDataGateway | None) -> "BrokerServiceTestBuilder":
        self._gateway = gateway
        return self

    def with_upstox_gateway(self, gateway: MarketDataGateway | None) -> "BrokerServiceTestBuilder":
        self._upstox_gateway = gateway
        return self

    def with_paper(self, paper: Any | None) -> "BrokerServiceTestBuilder":
        self._paper = paper
        return self

    def with_mock(self, mock: Any | None) -> "BrokerServiceTestBuilder":
        self._mock = mock
        return self

    def with_active_name(self, name: str) -> "BrokerServiceTestBuilder":
        self._active_name = name
        return self

    def with_dhan_load_error(self, error: str | None) -> "BrokerServiceTestBuilder":
        self._dhan_load_error = error
        return self

    def with_upstox_load_error(self, error: str | None) -> "BrokerServiceTestBuilder":
        self._upstox_load_error = error
        return self

    def with_initialized(self, initialized: bool = True) -> "BrokerServiceTestBuilder":
        self._initialized = initialized
        return self

    def with_trading_context(self, ctx: TradingContext | None) -> "BrokerServiceTestBuilder":
        self._trading_context = ctx
        return self

    def with_oms_proxy(self, proxy: OMSGatewayProxy | None) -> "BrokerServiceTestBuilder":
        self._oms_proxy = proxy
        return self

    def with_upstox_oms_proxy(self, proxy: OMSGatewayProxy | None) -> "BrokerServiceTestBuilder":
        self._upstox_oms_proxy = proxy
        return self

    def with_event_bus(self, bus: Any | None) -> "BrokerServiceTestBuilder":
        self._event_bus = bus
        return self

    def with_readonly(self, readonly: bool = True) -> "BrokerServiceTestBuilder":
        self._readonly = readonly
        return self

    def with_live_intent(self, live_intent: bool = True) -> "BrokerServiceTestBuilder":
        self._live_intent = live_intent
        return self

    def with_broker_infra(self, infra: Any | None) -> "BrokerServiceTestBuilder":
        self._broker_infra = infra
        return self

    def build(self) -> "BrokerService":
        instance: BrokerService = object.__new__(BrokerService)
        instance._gateway = self._gateway
        instance._upstox_gateway = self._upstox_gateway
        instance._paper = self._paper
        instance._mock = self._mock
        instance._active_name = self._active_name
        instance._dhan_load_error = self._dhan_load_error
        instance._upstox_load_error = self._upstox_load_error
        instance._initialized = self._initialized
        instance._trading_context = self._trading_context
        instance._oms_proxy = self._oms_proxy
        instance._upstox_oms_proxy = self._upstox_oms_proxy
        instance._oms_risk_manager = self._oms_risk_manager
        instance._risk_fail_open = self._risk_fail_open
        instance._capital_fallback_count = self._capital_fallback_count
        instance._lifecycle = self._lifecycle
        instance._broker_infra = self._broker_infra
        instance._http_observability = self._http_observability
        instance._readiness_report = self._readiness_report
        instance._load_instruments = self._load_instruments
        instance._event_bus = self._event_bus
        instance._readonly = self._readonly
        instance._live_intent = self._live_intent
        instance._dhan_bootstrap = self._dhan_bootstrap
        instance._upstox_bootstrap = self._upstox_bootstrap
        return instance

    @classmethod
    def create_test_double(cls, **overrides: Any) -> "BrokerService":
        """Deprecated: use ``BrokerServiceTestBuilder(...).build()`` instead.

        This classmethod is preserved for backward compatibility during the
        transition but will be removed in a future release.
        """
        import warnings

        warnings.warn(
            "BrokerService.create_test_double is deprecated; "
            "use BrokerServiceTestBuilder(...).build() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        builder = BrokerServiceTestBuilder()
        for key, value in overrides.items():
            setter = getattr(builder, f"with_{key}", None)
            if setter is None:
                raise ValueError(
                    f"Unknown attribute {key!r}. "
                    "Use the explicit with_*() methods on BrokerServiceTestBuilder."
                )
            setter(value)
        return builder.build()
