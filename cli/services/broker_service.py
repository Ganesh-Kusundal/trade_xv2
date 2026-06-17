"""Broker service layer — bridges CLI/TUI to the new BrokerGateway architecture."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from brokers.common.gateway import MarketDataGateway
from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms.context import TradingContext
from brokers.paper import PaperGateway

from cli.services.broker_registry import create_gateway

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

    def __init__(self) -> None:
        self._gateway: MarketDataGateway | None = None
        self._upstox_gateway: MarketDataGateway | None = None
        self._paper: PaperGateway | None = None
        self._mock: MockBroker | None = None
        self._active_name: str = "dhan"
        self._dhan_load_error: str | None = None
        self._upstox_load_error: str | None = None
        self._initialized = False
        self._trading_context: TradingContext | None = None
        self._http_observability = None  # B8+B9 followup
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
        from brokers.common.observability.http_server import (
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

        try:
            server = HttpObservabilityServer(
                host="127.0.0.1",
                port=8765,
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
                extra={"host": "127.0.0.1", "port": 8765},
            )
        except Exception as exc:
            logger.warning("http_observability_start_failed: %s", exc)
            self._http_observability = None

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
                oms_risk_manager = self._build_oms_risk_manager()
                # A5: pass the lifecycle so the factory registers
                # TokenRefreshScheduler with it (instead of starting
                # a bare daemon thread). The factory's backward-compat
                # path is intentionally bypassed here.
                self._gateway = create_gateway(
                    "dhan",
                    env_path=_ENV_PATH,
                    load_instruments=True,
                    lifecycle=self._lifecycle,
                    # B7: OMS risk_manager → OrdersAdapter risk gate.
                    risk_manager=oms_risk_manager,
                )
                # C.1: now that the gateway exists, point the OMS
                # capital_fn closure at it. From this point on, the
                # risk check uses the real account balance, not the
                # placeholder.
                if hasattr(self, "_oms_gateway_holder"):
                    self._oms_gateway_holder["gw"] = self._gateway
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
        upstox_env_path = Path(".env.upstox")
        if upstox_env_path.exists():
            try:
                self._upstox_gateway = create_gateway(
                    "upstox",
                    env_path=upstox_env_path,
                    load_instruments=True,
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
        """B-4: lazily create the market feed and order stream services
        via the connection factory so they are registered with the
        LifecycleManager and drained on close().

        Both services are ManagedService instances. The market feed
        reconnects with a 1s→30s backoff that now resets on every
        successful connect (B-4). The order stream gains a reconnect
        loop identical to the market feed (B-4).
        """
        conn = getattr(self._gateway, "_conn", None) if self._gateway else None
        if conn is None:
            return
        # Subscribe to the canonical NSE_EQ NIFTY spot feed so the
        # OMS has streaming state to publish. In production this would
        # be driven by the strategy engine.
        try:
            from brokers.dhan.websocket import DhanOrderStream

            def access_token_fn():
                return conn._client.access_token
            # Order stream: always start — used by the OMS for fill
            # detection on every place_order call.
            if conn.order_stream is None:
                stream = DhanOrderStream(
                    client_id=conn._client.client_id,
                    access_token=conn._client.access_token,
                    access_token_fn=access_token_fn,
                    event_bus=conn.event_bus,
                )
                conn.order_stream = stream
                try:
                    self._lifecycle.register(stream)
                except Exception as exc:  # pragma: no cover
                    logger.debug("order_stream_register_failed: %s", exc)
            # Market feed: only create if a strategy subscribes;
            # placeholder keeps the lifecycle slot reserved. The
            # previous broker.gateway.stream() helper still creates
            # on demand.
        except Exception as exc:
            logger.warning("websocket_services_wiring_failed: %s", exc)

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

        from brokers.common.oms import PositionManager, RiskConfig, RiskManager

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
        ``EventLog`` into the live CLI path. Previously the
        ``reconciliation_service`` argument was omitted, so the OMS
        timer thread called a no-op broker and drift detection was
        off; and the ``event_log`` argument was omitted, so the
        DH-906-recovery replay was dead code.
        """
        from brokers.common.event_log import EventLog
        from brokers.common.oms import (
            DailyPnlResetScheduler,
            create_trading_context,
        )

        # DailyPnlResetScheduler — clears _daily_pnl at IST 00:00.
        # Register with the lifecycle so it is drained on close().
        scheduler = DailyPnlResetScheduler(risk_manager=risk_manager)
        try:
            self._lifecycle.register(scheduler)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("lifecycle_register_failed: %s", exc)

        # B-1: build a DhanReconciliationService backed by the gateway
        # orders + portfolio adapters. The OMS's ReconciliationService
        # timer thread will call this every 300s. Drift items are
        # surfaced in /metrics as ``reconciliation_drift_count``.
        dhan_reconciliation = None
        try:
            from brokers.dhan.reconciliation import (
                create_reconciliation_service,
            )
            conn = getattr(self._gateway, "_conn", None)
            if conn is not None:
                dhan_reconciliation = create_reconciliation_service(
                    orders_adapter=conn.orders,
                    portfolio_adapter=conn.portfolio,
                    oms=None,  # set below once OrderManager exists
                    auto_repair=False,
                )
        except Exception as exc:
            logger.warning("dhan_reconciliation_build_failed: %s", exc)

        # B-2: build an EventLog for crash recovery and OMS replay on
        # startup. The TradingContext wires this into the EventBus.
        try:
            event_log = EventLog(events_dir=Path("runtime/event-log"))
        except Exception as exc:
            logger.error("event_log_build_failed: %s", exc)
            event_log = None

        # Build a TradingContext that shares the OMS risk_manager,
        # reconciliation, and event_log with the lifecycle. The Dhan
        # OrdersAdapter is already wired to the same risk_manager via
        # the factory, so a single risk check covers every place_order
        # path.
        try:
            self._trading_context = create_trading_context(
                risk_manager=risk_manager,
                reconciliation_service=dhan_reconciliation,
                reconciliation_interval_seconds=300.0,
                event_log=event_log,
                replay_events=event_log is not None,
            )
            # Attach any registered ManagedServices (reconciliation)
            # to the lifecycle.
            self._trading_context.attach_lifecycle(self._lifecycle)
            # Now that the OrderManager exists, point the
            # DhanReconciliationService at it for auto_repair=False
            # (we only want to surface drift; the operator decides).
            if dhan_reconciliation is not None:
                dhan_reconciliation._oms = self._trading_context.order_manager
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("trading_context_build_failed: %s", exc)
            self._trading_context = None

    @property
    def trading_context(self) -> TradingContext | None:
        """Return the shared TradingContext (may be *None* before init)."""
        self._ensure_initialized()
        return self._trading_context

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
