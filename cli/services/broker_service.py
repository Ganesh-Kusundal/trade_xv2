"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture."""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path

from domain import Order, Side
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from infrastructure.lifecycle.lifecycle import LifecycleManager
from application.oms.context import TradingContext
from cli.services.broker_registry import (
    create_seeded_mock_broker,
    get_dhan_reconciliation_service_factory,
    get_dhan_websocket_classes,
    get_mock_broker_class,
    get_paper_gateway_class,
)

# Concrete broker classes are obtained via the registry (the sole cli module
# permitted to import broker implementations) rather than imported directly,
# to satisfy the CLI broker-implementation isolation contract.
PaperGateway = get_paper_gateway_class()
MockBroker = get_mock_broker_class()

from cli.services.broker_registry import bootstrap_gateway, create_gateway, resolve_env_path
from domain.errors import BrokerNotReadyError
from domain.ports.bootstrap import BootstrapResult, BootstrapStatus
from cli.services.broker_observability import (
    compute_live_actionable,
    resolve_active_broker,
)

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
        # Two paths can authorise the override:
        #   1. ``authorize_risk_fail_open=True`` passed by the CLI when the
        #      operator has explicitly typed ``--risk-fail-open``.
        #   2. ``RISK_FAIL_OPEN=1`` in the process environment AND a
        #      matching ``--risk-fail-open`` CLI flag.
        # Setting the env var alone is refused at startup. This prevents
        # a stale ``.env.local`` value from silently authorising the legacy
        # 1,000,000 INR placeholder against an unknown balance.
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
        # and emitted as a Prometheus gauge by the HTTP server. The placeholder
        # is NEVER used silently again.
        self._capital_fallback_count: int = 0
        # A5: every background service in the system is owned by this
        # LifecycleManager. Created eagerly so close() can stop_all()
        # even if _ensure_initialized() failed midway.
        self._lifecycle = LifecycleManager()
        # M-7 / Phase 1.2: production readiness gate result. False until
        # ``_ensure_initialized`` runs and ``run_or_raise`` succeeds.
        # ``BrokerService.place_order`` refuses to dispatch when False.
        self._live_actionable: bool = False
        self._readiness_report: Any = None

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
    def http_observability(self):
        """The HTTP observability server (Phase B / B8+B9).

        Returns ``None`` before init or if the server failed to start.
        Exposed so the CLI's ``doctor`` and ``metrics`` commands
        (future work) can introspect it.
        """
        return self._http_observability

    def _start_http_observability_server(self, risk_manager) -> None:
        """B8+B9 followup: spin up the HTTP observability server.

        Constructs an :class:`HttpObservabilityServer` with the OMS's
        ``EventMetrics`` (so /metrics shows the same counters the
        OMS increments) and a ``extra_gauges_fn`` that returns the
        OMS risk state (daily_pnl, kill_switch, etc.). Registers
        the server with the lifecycle so close() drains it.

        Best-effort: if the bind fails (port in use) the service
        is left as None and a warning is logged. Production
        observability must not block init.
        """
        from tradex.runtime.observability.http_server import (
            HttpObservabilityServer,
        )

        # Share the OMS's EventMetrics so /metrics shows the same
        # counters the OMS increments. If the TradingContext is
        # None (init failed), fall back to a fresh EventMetrics.
        event_metrics = None
        if self._trading_context is not None:
            event_metrics = self._trading_context.metrics

        def _extra_gauges() -> dict[str, float]:
            """Return OMS risk state as Prometheus gauges."""
            if risk_manager is None:
                return {}
            try:
                snap = risk_manager.snapshot()
            except Exception:
                return {}

            def _f(v: object) -> float:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0

            gauges: dict[str, float] = {
                "daily_pnl": _f(snap.get("daily_pnl", "0")),
                "kill_switch_active": 1.0 if snap.get("kill_switch") else 0.0,
                "kill_switch_toggles": _f(snap.get("kill_switch_toggles", 0)),
                "reset_count": _f(snap.get("reset_count", 0)),
                # M-7: fail-open override flag, 1 when operator has explicitly
                # opted into the legacy 1,000,000 placeholder.
                "risk_fail_open_active": 1.0 if self._risk_fail_open else 0.0,
            }
            # M-4: extra visibility for ops — capital fallback, drift, DLQ depth,
            # circuit-breaker state, websocket connectivity.
            try:
                gauges["capital_fallback_count"] = float(
                    getattr(self, "_capital_fallback_count", 0)
                )
            except Exception as exc:
                logger.debug("capital_fallback_gauge_failed: %s", exc)
            ctx = getattr(self, "_trading_context", None)
            if ctx is not None:
                dlq = getattr(ctx, "dead_letter_queue", None)
                if dlq is not None:
                    try:
                        gauges["dlq_depth"] = float(len(dlq.entries))
                        gauges["dlq_dropped"] = float(getattr(dlq, "dropped", 0))
                    except Exception as exc:
                        logger.debug("dlq_gauge_failed: %s", exc)
                recon = getattr(ctx, "_reconciliation_service", None)
                if recon is not None:
                    try:
                        gauges["reconciliation_drift_count"] = float(
                            recon.last_drift_count
                        )
                        gauges["reconciliation_run_count"] = float(
                            recon.run_count
                        )
                    except Exception as exc:
                        logger.debug("reconciliation_gauge_failed: %s", exc)
                if getattr(ctx, "_event_log", None) is not None:
                    gauges["event_log_replay_count"] = float(
                        getattr(ctx._event_log, "replay_count", 0)
                    )
            conn = getattr(self._gateway, "_conn", None) if self._gateway else None
            if conn is not None:
                mf = getattr(conn, "market_feed", None)
                if mf is not None:
                    gauges["market_stream_connected"] = 1.0 if mf.is_connected else 0.0
                os_ = getattr(conn, "order_stream", None)
                if os_ is not None:
                    gauges["order_stream_connected"] = 1.0 if os_.is_connected else 0.0
                # Token refresh metrics
                scheduler = getattr(conn, "_token_scheduler", None)
                if scheduler is not None:
                    try:
                        gauges["token_refresh_count"] = float(
                            getattr(scheduler, "refresh_count", 0)
                        )
                        gauges["token_refresh_last_error"] = 1.0 if getattr(scheduler, "_last_error", None) else 0.0
                    except Exception as exc:
                        logger.debug("token_refresh_gauge_failed: %s", exc)
            client = getattr(conn, "_client", None) if conn is not None else None
            if client is not None:
                for name, cb in (
                    ("cb_dhan_read", getattr(client, "_read_circuit_breaker", None)),
                    ("cb_dhan_write", getattr(client, "_write_circuit_breaker", None)),
                    ("cb_dhan_admin", getattr(client, "_admin_circuit_breaker", None)),
                ):
                    if cb is not None:
                        try:
                            gauges[name] = float(
                                getattr(cb, "state", 0).value
                                if hasattr(getattr(cb, "state", 0), "value")
                                else 0
                            )
                        except Exception as exc:
                            logger.debug("circuit_breaker_gauge_failed: %s", exc)
            return gauges

        # Phase 1.3: HTTP observability is a hard requirement for the live
        # path. The port is configurable via ``TRADEX_METRICS_PORT`` so two
        # instances on the same host can coexist; the default is 8765.
        # A bind failure (port in use, permission denied) marks the runtime
        # as ``not live-actionable`` so the production readiness gate
        # surfaces the problem rather than silently disabling /healthz,
        # /readyz, and /metrics.
        metrics_port_env = os.environ.get("TRADEX_METRICS_PORT")
        try:
            metrics_port = int(metrics_port_env) if metrics_port_env else 8765
        except ValueError:
            logger.warning(
                "TRADEX_METRICS_PORT_invalid: %r — falling back to 8765",
                metrics_port_env,
            )
            metrics_port = 8765

        try:
            server = HttpObservabilityServer(
                host="127.0.0.1",
                port=metrics_port,
                lifecycle=self._lifecycle,
                event_metrics=event_metrics,
                extra_gauges_fn=_extra_gauges,
            )
            server.start()
            try:
                self._lifecycle.register(server)
            except Exception as exc:  # pragma: no cover - duplicate name
                logger.debug("http_server_register_failed: %s", exc)
            self._http_observability = server
            logger.info(
                "http_observability_started",
                extra={"host": "127.0.0.1", "port": metrics_port},
            )
        except Exception as exc:
            # Phase 1.3: do NOT silently disable observability. Log at
            # ERROR so the doctor command and the production readiness
            # gate (``_check_http_observability``) can surface the
            # failure, and mark the runtime as not live-actionable.
            logger.error(
                "http_observability_start_failed: %s — live-actionable=False",
                exc,
            )
            self._http_observability = None
            self._live_actionable = False

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
                # (and at most one TOTP remint if token rejected).
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
                    # Only start lifecycle when auth probe passed
                    self._lifecycle.start_all()
                    self._start_http_observability_server(oms_risk_manager)
                    from tradex.runtime.services.production_readiness import (
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

    def _start_websocket_services(self) -> None:
        """B-4 / Phase 1.5: register both the market feed and order
        stream with the LifecycleManager so they participate in
        deterministic start/stop and the reconnect backoff never
        escapes the process.

        Both services are ManagedService instances. The previous
        implementation only wired the order stream; the market feed
        was created lazily by ``gateway.stream()`` and was therefore
        NOT lifecycle-owned. A consumer that subscribed and then
        exited without calling ``stream.stop()`` would leak the
        daemon thread. Phase 1.5 closes that hole by registering both
        via the connection factory (``create_market_feed`` and
        ``create_order_stream``) which self-register with the
        lifecycle if a LifecycleManager was supplied at construction.
        """
        conn = getattr(self._gateway, "_conn", None) if self._gateway else None
        if conn is None:
            return
        try:
            DhanMarketFeed, DhanOrderStream = get_dhan_websocket_classes()

            def access_token_fn():
                return conn._client.access_token

            # Order stream: required for fill detection on every
            # place_order call. create_order_stream auto-registers
            # with the lifecycle.
            if conn.order_stream is None and DhanOrderStream is not None:
                conn.create_order_stream(
                    access_token=conn._client.access_token,
                    access_token_fn=access_token_fn,
                )

            # Market feed: default-subscribe to the canonical NIFTY 50
            # index (Dhan segment IDX, security_id 13) so the OMS has a
            # streaming reference instrument. create_market_feed
            # auto-registers with the lifecycle. Operators can extend
            # the subscription via ``feed.subscribe([...])`` later.
            if conn.market_feed is None and DhanMarketFeed is not None:
                # Best-effort: if the instrument is not resolvable the
                # feed is created empty and the production readiness
                # gate (``_check_market_feed``) surfaces the
                # misconfiguration.
                instruments: list[tuple] = []
                try:
                    inst = conn.instruments.resolve("NIFTY", "IDX")
                    if inst is not None:
                        instruments = [("IDX_I", str(inst.security_id), "QUOTE")]
                except Exception as exc:
                    logger.debug(
                        "nifty_spot_resolve_skipped: %s", exc,
                    )
                conn.create_market_feed(
                    access_token=conn._client.access_token,
                    access_token_fn=access_token_fn,
                    instruments=instruments,
                )
        except Exception as exc:
            logger.error("websocket_services_wiring_failed: %s", exc)

    def _build_oms_risk_manager(self):
        """B7: build a RiskManager for the OMS that the live path
        will consult.

        C.1 (Phase C): the capital_fn is now wired to the real
        ``gateway.funds().available_balance`` once the gateway is
        constructed. The closure captures the gateway by reference via
        ``self._oms_gateway_holder``, which ``_ensure_initialized``
        populates after the factory call returns. This is the central
        risk-calibration invariant: the daily_loss_pct and
        position_pct checks are sized to the real account, not a
        placeholder.

        B-3 / M-7 (2026-06-15): the legacy ``Decimal("1000000")`` silent
        placeholder has been removed. The capital_fn now:

          * Returns the real broker balance when available.
          * On any failure (init incomplete, broker call exception,
            zero/negative balance), increments
            ``self._capital_fallback_count`` and emits a WARNING.
          * Returns ``Decimal(0)`` — which the OMS interprets as
            "Insufficient capital" and BLOCKS every order — UNLESS
            ``RISK_FAIL_OPEN=1`` is set in the environment, in which
            case the operator has explicitly authorised the legacy
            1,000,000 placeholder. The override is logged at WARNING
            and exposed as a Prometheus gauge
            (``risk_fail_open_active``).

        This is a fail-safe design: no order can be placed against an
        unknown capital baseline unless the operator has explicitly
        opted into fail-open mode.
        """
        from decimal import Decimal

        from application.oms._internal.risk_manager import RiskConfig, RiskManager
        from application.oms.position_manager import PositionManager

        # The gateway is set after the factory returns. Use a mutable
        # holder so the closure can read the live reference.
        if not hasattr(self, "_oms_gateway_holder") or self._oms_gateway_holder is None:
            self._oms_gateway_holder: dict = {"gw": None}

        def _capital_fn() -> Decimal:
            gw = self._oms_gateway_holder.get("gw")
            if gw is None:
                # Init not yet complete or gateway construction failed.
                # B-3: fail closed — return 0 so RiskManager blocks every
                # order. Operator must set RISK_FAIL_OPEN=1 to override.
                self._capital_fallback_count += 1
                if self._risk_fail_open:
                    logger.warning(
                        "risk_capital_using_placeholder",
                        extra={
                            "reason": "gateway_not_constructed",
                            "placeholder": "Decimal('1000000')",
                            "fallback_count": self._capital_fallback_count,
                        },
                    )
                    return Decimal("1000000")
                logger.error(
                    "risk_capital_blocking",
                    extra={
                        "reason": "gateway_not_constructed",
                        "fallback_count": self._capital_fallback_count,
                        "override": "set RISK_FAIL_OPEN=1 to allow",
                    },
                )
                return Decimal("0")

            try:
                balance = gw.funds()
            except Exception as exc:
                # Broker call failed (network, auth, etc.). B-3: fail closed
                # by default; allow override via RISK_FAIL_OPEN=1.
                self._capital_fallback_count += 1
                if self._risk_fail_open:
                    logger.warning(
                        "risk_capital_using_placeholder",
                        extra={
                            "reason": f"funds_call_failed:{type(exc).__name__}",
                            "placeholder": "Decimal('1000000')",
                            "fallback_count": self._capital_fallback_count,
                        },
                    )
                    return Decimal("1000000")
                logger.error(
                    "risk_capital_blocking",
                    extra={
                        "reason": f"funds_call_failed:{type(exc).__name__}",
                        "fallback_count": self._capital_fallback_count,
                        "override": "set RISK_FAIL_OPEN=1 to allow",
                    },
                )
                return Decimal("0")

            balance_value = getattr(balance, "available_balance", None)
            if balance_value is None or balance_value <= 0:
                # B-3: zero/negative balance is a hard stop, even with
                # RISK_FAIL_OPEN. A phantom capital would defeat the risk
                # gate. The operator must wait for a positive balance.
                self._capital_fallback_count += 1
                logger.error(
                    "risk_capital_blocking",
                    extra={
                        "reason": f"balance_non_positive:{balance_value}",
                        "fallback_count": self._capital_fallback_count,
                    },
                )
                return Decimal("0")
            return balance_value

        return RiskManager(
            position_manager=PositionManager(),
            config=RiskConfig(),
            capital_fn=_capital_fn,
        )

    def _build_and_register_oms_services(self, risk_manager) -> None:
        """B7: construct the OMS-side services (DailyPnlResetScheduler,
        OMS TradingContext) and register them with the lifecycle so
        they are drained on close().

        The TradingContext holds the canonical ``OrderManager``,
        ``PositionManager``, ``RiskManager``, ``EventBus``, and
        ``ProcessedTradeRepository``. It is the single source of truth
        for order state on the live CLI path.

        B-1 / B-2 (2026-06-15): wires ``DhanReconciliationService`` and
        ``EventLog`` into the live CLI path.

        Phase 1.4: builds the TradingContext FIRST (so the OrderManager
        reference exists) and THEN attaches the broker-specific
        reconciliation service via
        ``TradingContext.attach_reconciliation_service``. The previous
        implementation monkey-patched ``dhan_reconciliation._oms =
        order_manager`` AFTER building the TradingContext, which left
        drift detection silently disabled if the TradingContext build
        raised between the two steps.
        """
        from infrastructure.event_log import EventLog
        from application.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler
        from application.oms.factory import create_trading_context

        # DailyPnlResetScheduler — clears _daily_pnl at IST 00:00.
        # Register with the lifecycle so it is drained on close().
        scheduler = DailyPnlResetScheduler(risk_manager=risk_manager)
        try:
            self._lifecycle.register(scheduler)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("lifecycle_register_failed: %s", exc)

        # B-2: build an EventLog for crash recovery and OMS replay on
        # startup. The TradingContext wires this into the EventBus.
        try:
            event_log = EventLog(events_dir=Path("runtime/event-log"))
        except Exception as exc:
            logger.error("event_log_build_failed: %s", exc)
            event_log = None

        # Build a TradingContext that shares the OMS risk_manager
        # and event_log with the lifecycle. The Dhan OrdersAdapter is
        # already wired to the same risk_manager via the factory, so a
        # single risk check covers every place_order path.
        #
        # ``reconciliation_service`` is intentionally omitted here — we
        # attach the broker-specific reconciler AFTER the TradingContext
        # is built so the OrderManager reference is live (see Phase 1.4).
        try:
            self._trading_context = create_trading_context(
                risk_manager=risk_manager,
                reconciliation_service=None,
                reconciliation_interval_seconds=300.0,
                event_log=event_log,
                replay_events=event_log is not None,
            )
            # Attach any registered ManagedServices (none yet) to the
            # lifecycle. The reconciliation service is attached below
            # via the explicit setter once it is built.
            self._trading_context.attach_lifecycle(self._lifecycle)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("trading_context_build_failed: %s", exc)
            self._trading_context = None
            return

        # B-1 (Phase 1.4): now that the OrderManager exists, build the
        # broker-specific DhanReconciliationService and attach it via
        # the explicit setter. This replaces the previous monkey-patch
        # (``dhan_reconciliation._oms = order_manager``) which left drift
        # detection silently disabled if any earlier step raised.
        try:
            create_reconciliation_service = get_dhan_reconciliation_service_factory()
            conn = getattr(self._gateway, "_conn", None)
            if conn is not None:
                from application.oms.recon_heal_policy import should_auto_repair

                dhan_reconciliation = create_reconciliation_service(
                    orders_adapter=conn.orders,
                    portfolio_adapter=conn.portfolio,
                    oms=self._trading_context.order_manager,
                    auto_repair=should_auto_repair(),
                )
                # Allow heal path to upsert positions via PositionManager
                self._trading_context.order_manager.position_manager = (
                    self._trading_context.position_manager
                )
                self._trading_context.attach_reconciliation_service(
                    dhan_reconciliation,
                    lifecycle=self._lifecycle,
                )
        except Exception as exc:
            logger.error("dhan_reconciliation_attach_failed: %s", exc)

    @property
    def trading_context(self) -> TradingContext | None:
        """Return the shared TradingContext (may be *None* before init)."""
        self._ensure_initialized()
        return self._trading_context

    # -- properties ---------------------------------------------------------

    @property
    def active_broker(self) -> MarketDataGateway | PaperGateway | MockBroker:
        """Return the active broker: live Dhan, live Upstox, paper, or mock.

        Raises BrokerNotReadyError when the selected live broker failed
        authenticated bootstrap and no paper/mock fallback is appropriate.
        """
        self._ensure_initialized()
        # Live selection that failed auth must not silently fall back to mock
        # when operator explicitly selected dhan/upstox after a failed bootstrap.
        if (
            self._active_name == "dhan"
            and self._gateway is None
            and self._dhan_bootstrap is not None
            and self._dhan_bootstrap.status
            in {BootstrapStatus.REAUTH_REQUIRED, BootstrapStatus.FAILED}
        ):
            raise BrokerNotReadyError.from_bootstrap(self._dhan_bootstrap)
        if (
            self._active_name == "upstox"
            and self._upstox_gateway is None
            and self._upstox_bootstrap is not None
            and self._upstox_bootstrap.status
            in {BootstrapStatus.REAUTH_REQUIRED, BootstrapStatus.FAILED}
        ):
            raise BrokerNotReadyError.from_bootstrap(self._upstox_bootstrap)

        return resolve_active_broker(
            self._active_name,
            paper=self._paper,
            oms_proxy=None,
            gateway=self._gateway,
            upstox_oms_proxy=None,
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
    def is_live_dhan_active(self) -> bool:
        """``True`` when a real ``BrokerGateway`` is connected (not mock)."""
        self._ensure_initialized()
        return self._gateway is not None

    @property
    def live_actionable(self) -> bool:
        """``True`` when the runtime is safe to place live orders.

        The runtime is ``live_actionable`` only when:

        * The Dhan gateway was constructed without error, AND
        * The OMS services (reconciliation, event log) are wired, AND
        * Both WebSocket services (market feed + order stream) are
          registered with the LifecycleManager, AND
        * The HTTP observability server is running, AND
        * The risk manager has a real capital source (no phantom fallback
          unless ``--risk-fail-open`` was set explicitly), AND
        * All required credentials are present.

        When this property is ``False`` the CLI may still run read-only
        diagnostic commands (``quote``, ``depth``, ``historical``,
        ``instruments``, ``broker list``, ``doctor``) but every
        ``BrokerService.place_order`` call refuses with a structured error.
        """
        self._ensure_initialized()
        return self._live_actionable

    @property
    def readiness_report(self):
        """The most recent :class:`ReadinessReport` from the production
        readiness gate, or ``None`` if init has not run yet."""
        self._ensure_initialized()
        return self._readiness_report

    @property
    def dhan_load_error(self) -> str | None:
        return self._dhan_load_error

    # -- OMS delegate methods (D6: absorbed OmsService responsibilities) -----
    # Decision #7 retires cli/services/oms_service.py; its two responsibilities
    # (the live_actionable guard + order/trade read + write access) are inlined
    # here, since BrokerService already owns the TradingContext. Behavior is
    # kept identical to the retired OmsService.

    def _oms_orders(self) -> list:
        """Return orders from the central OrderManager, falling back to the
        gateway order book when no TradingContext is wired (backward compat)."""
        self._ensure_initialized()
        if self._trading_context is not None:
            return self._trading_context.order_manager.get_orders()
        gw = self._gateway
        if gw is None:
            return []
        return gw.get_orderbook()

    def _oms_trades(self) -> list:
        self._ensure_initialized()
        gw = self._gateway
        if gw is None:
            return []
        return gw.get_trade_book()

    def _ensure_oms_gateway(self):
        self._ensure_initialized()
        gw = self._gateway
        if gw is None:
            if self._trading_context is not None:
                raise RuntimeError("TradingContext does not expose a gateway.")
            raise RuntimeError(
                "No broker gateway available. Configure .env.local with valid credentials."
            )
        return gw

    def get_order_stats(self) -> dict[str, int]:
        """Collect order counts by status (mirrors retired OmsService)."""
        from domain import OrderStatus

        orders = self._oms_orders()
        stats = {
            "pending": 0,
            "open": 0,
            "filled": 0,
            "rejected": 0,
            "cancelled": 0,
        }
        for o in orders:
            status = o.status
            if status == OrderStatus.OPEN:
                stats["open"] += 1
            elif status == OrderStatus.PARTIALLY_FILLED:
                stats["pending"] += 1
            elif status == OrderStatus.FILLED:
                stats["filled"] += 1
            elif status == OrderStatus.REJECTED:
                stats["rejected"] += 1
            elif status == OrderStatus.CANCELLED:
                stats["cancelled"] += 1
        return stats

    def get_orders(self, status_filter: str | None = None) -> list:
        """Fetch orders with optional status filter (mirrors retired OmsService)."""
        from domain import OrderStatus

        orders = self._oms_orders()
        if not status_filter:
            return orders

        filt = status_filter.upper()
        if filt == "PENDING":
            return [
                o for o in orders if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
            ]
        if filt == "FILLED":
            return [o for o in orders if o.status == OrderStatus.FILLED]
        return [o for o in orders if o.status.value == filt]

    def get_trades(self) -> list:
        """Fetch trades for the day (mirrors retired OmsService)."""
        return self._oms_trades()

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 0,
        price: Decimal | None = None,
        order_type: str = "MARKET",
    ) -> Order:
        """Place order via the OMS OrderManager.

        The central OMS is the SINGLE entry point for order placement. The
        broker gateway is consulted by the OMS's ``submit_fn`` (which the OMS
        uses to dispatch to Dhan), so callers do not bypass risk checks,
        idempotency, or event-bus publishing.

        This method refuses to dispatch when the runtime is not
        ``live_actionable`` (production readiness gate failed, or the OMS has
        not been wired into a ``TradingContext``).
        """
        self._ensure_initialized()
        if not self._live_actionable:
            raise RuntimeError(
                "OMS refused: runtime is not live-actionable. "
                "Run `tradex doctor` for the production readiness report; "
                "address every failing check before placing orders."
            )
        if self._trading_context is not None:
            from domain import (
                OrderType as Ot,
            )
            from domain import (
                ProductType as Pt,
            )
            from application.oms.order_manager import OrderRequest

            try:
                ot = Ot(order_type)
            except ValueError:
                ot = Ot.MARKET
            req = OrderRequest(
                symbol=symbol,
                exchange=exchange,
                side=Side(side) if isinstance(side, str) else side,
                quantity=quantity,
                price=price if price is not None else Decimal("0"),
                order_type=ot,
                product_type=Pt.INTRADAY,
            )
            gw = self._gateway
            if gw is None:
                raise RuntimeError(
                    "No broker gateway available. Configure .env.local with valid credentials."
                )

            def _submit(r: OrderRequest) -> Order:
                return gw.place_order(
                    symbol=r.symbol,
                    exchange=r.exchange,
                    side=r.side,
                    quantity=r.quantity,
                    price=r.price,
                    order_type=r.order_type,
                    product_type=r.product_type,
                )

            result = self._trading_context.order_manager.place_order(req, submit_fn=_submit)
            if not result.success:
                raise RuntimeError(f"OMS rejected order: {result.error}")
            return result.order
        # Safe-to-trade: never bypass OMS (no bare gateway place_order)
        raise RuntimeError(
            "OMS refused: TradingContext / OrderManager not wired. "
            "Cannot place orders without the institutional order spine."
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order (mirrors retired OmsService)."""
        self._ensure_initialized()
        if self._trading_context is not None:
            result = self._trading_context.order_manager.cancel_order(order_id)
            return result.success
        raise RuntimeError(
            "OMS refused: TradingContext / OrderManager not wired. "
            "Cannot cancel orders without the institutional order spine."
        )

    # -- broker management --------------------------------------------------

    def set_active_broker(self, name: str) -> None:
        self._ensure_initialized()
        name_lower = name.lower()
        if name_lower == "paper":
            if self._paper is None:
                self._paper = PaperGateway()
            self._active_name = "paper"
        elif name_lower == "dhan":
            if self._gateway is None:
                raise ValueError("Dhan broker not available. Check .env.local credentials.")
            self._active_name = "dhan"
        elif name_lower == "upstox":
            if self._upstox_gateway is None:
                raise ValueError("Upstox broker not available. Check .env.upstox credentials.")
            self._active_name = "upstox"
        elif name_lower == "datalake":
            # Phase 6: read-only datalake gateway. Created lazily so
            # operators can switch between live and historical data
            # without restarting the CLI.
            from cli.services.broker_registry import create_gateway
            self._paper = create_gateway("datalake", load_instruments=False)
            if self._paper is None:
                raise ValueError(
                    "DataLake gateway not available. Verify the 'market_data' directory exists."
                )
            self._active_name = "datalake"
        else:
            raise ValueError(
                f"Broker '{name}' is not registered. Use 'dhan', 'upstox', 'paper', or 'datalake'."
            )
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
        # Phase 6: read-only datalake gateway. Marked as Available
        # when the local Parquet directory exists, otherwise the
        # operator gets a hint to bootstrap it.
        from pathlib import Path as _Path
        datalake_status = (
            "Available" if _Path("market_data").exists() else "Directory not found"
        )
        statuses.append({"broker": "DataLake (read-only)", "status": datalake_status})
        return statuses

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
