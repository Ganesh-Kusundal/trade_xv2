"""OMS Bootstrap — OMS setup, DI wiring, risk manager construction.

Extracted from BrokerService to reduce complexity and enable independent
testing.  This module handles:

- RiskManager construction with capital_fn (fail-open / fail-closed)
- WebSocket service wiring (market feed + order stream)
- TradingContext creation, reconciliation attach, and lifecycle registration
- HTTP observability server startup with Prometheus gauges
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from interface.ui.services.broker_registry import get_dhan_reconciliation_service_factory, get_dhan_websocket_classes

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


class OmsBootstrap:
    """Constructs and wires the OMS infrastructure.

    Every method receives the owning :class:`BrokerService` via the
    constructor so it can read / mutate shared state (gateway,
    trading_context, lifecycle, etc.).
    """

    def __init__(self, service: BrokerService) -> None:
        self._svc = service

    # ------------------------------------------------------------------
    # RiskManager
    # ------------------------------------------------------------------

    def build_risk_manager(self):
        """B7: build a RiskManager for the OMS that the live path
        will consult.

        C.1 (Phase C): the capital_fn is now wired to the real
        ``gateway.funds().available_balance`` once the gateway is
        constructed. The closure captures the gateway by reference via
        ``self._svc._oms_gateway_holder``, which ``_ensure_initialized``
        populates after the factory call returns. This is the central
        risk-calibration invariant: the daily_loss_pct and
        position_pct checks are sized to the real account, not a
        placeholder.

        B-3 / M-7 (2026-06-15): the legacy ``Decimal("1000000")`` silent
        placeholder has been removed. The capital_fn now:

          * Returns the real broker balance when available.
          * On any failure (init incomplete, broker call exception,
            zero/negative balance), increments
            ``self._svc._capital_fallback_count`` and emits a WARNING.
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
        from application.oms._internal.risk_manager import RiskConfig, RiskManager
        from application.oms.position_manager import PositionManager

        svc = self._svc

        # The gateway is set after the factory returns. Use a mutable
        # holder so the closure can read the live reference.
        if not hasattr(svc, "_oms_gateway_holder") or svc._oms_gateway_holder is None:
            svc._oms_gateway_holder: dict = {"gw": None}  # type: ignore[assignment]

        def _capital_fn() -> Decimal:
            gw = svc._oms_gateway_holder.get("gw")
            if gw is None:
                # Init not yet complete or gateway construction failed.
                # B-3: fail closed — return 0 so RiskManager blocks every
                # order. Operator must set RISK_FAIL_OPEN=1 to override.
                svc._capital_fallback_count += 1
                if svc._risk_fail_open:
                    logger.warning(
                        "risk_capital_using_placeholder",
                        extra={
                            "reason": "gateway_not_constructed",
                            "placeholder": "Decimal('1000000')",
                            "fallback_count": svc._capital_fallback_count,
                        },
                    )
                    return Decimal("1000000")
                logger.error(
                    "risk_capital_blocking",
                    extra={
                        "reason": "gateway_not_constructed",
                        "fallback_count": svc._capital_fallback_count,
                        "override": "set RISK_FAIL_OPEN=1 to allow",
                    },
                )
                return Decimal("0")

            try:
                balance = gw.funds()
            except Exception as exc:
                # Broker call failed (network, auth, etc.). B-3: fail closed
                # by default; allow override via RISK_FAIL_OPEN=1.
                svc._capital_fallback_count += 1
                if svc._risk_fail_open:
                    logger.warning(
                        "risk_capital_using_placeholder",
                        extra={
                            "reason": f"funds_call_failed:{type(exc).__name__}",
                            "placeholder": "Decimal('1000000')",
                            "fallback_count": svc._capital_fallback_count,
                        },
                    )
                    return Decimal("1000000")
                logger.error(
                    "risk_capital_blocking",
                    extra={
                        "reason": f"funds_call_failed:{type(exc).__name__}",
                        "fallback_count": svc._capital_fallback_count,
                        "override": "set RISK_FAIL_OPEN=1 to allow",
                    },
                )
                return Decimal("0")

            balance_value = getattr(balance, "available_balance", None)
            if balance_value is None or balance_value <= 0:
                # B-3: zero/negative balance is a hard stop, even with
                # RISK_FAIL_OPEN. A phantom capital would defeat the risk
                # gate. The operator must wait for a positive balance.
                svc._capital_fallback_count += 1
                logger.error(
                    "risk_capital_blocking",
                    extra={
                        "reason": f"balance_non_positive:{balance_value}",
                        "fallback_count": svc._capital_fallback_count,
                    },
                )
                return Decimal("0")
            return balance_value

        return RiskManager(
            position_manager=PositionManager(),
            config=RiskConfig(),
            capital_fn=_capital_fn,
        )

    # ------------------------------------------------------------------
    # TradingContext + reconciliation + event log
    # ------------------------------------------------------------------

    def build_and_register_services(self, risk_manager) -> None:
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

        svc = self._svc

        # DailyPnlResetScheduler — clears _daily_pnl at IST 00:00.
        # Register with the lifecycle so it is drained on close().
        scheduler = DailyPnlResetScheduler(risk_manager=risk_manager)
        try:
            svc._lifecycle.register(scheduler)
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
            svc._trading_context = create_trading_context(
                risk_manager=risk_manager,
                reconciliation_service=None,
                reconciliation_interval_seconds=300.0,
                event_log=event_log,
                replay_events=event_log is not None,
            )
            # Attach any registered ManagedServices (none yet) to the
            # lifecycle. The reconciliation service is attached below
            # via the explicit setter once it is built.
            svc._trading_context.attach_lifecycle(svc._lifecycle)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("trading_context_build_failed: %s", exc)
            svc._trading_context = None
            return

        # B-1 (Phase 1.4): now that the OrderManager exists, build the
        # broker-specific DhanReconciliationService and attach it via
        # the explicit setter. This replaces the previous monkey-patch
        # (``dhan_reconciliation._oms = order_manager``) which left drift
        # detection silently disabled if any earlier step raised.
        try:
            create_reconciliation_service = get_dhan_reconciliation_service_factory()
            conn = getattr(svc._gateway, "_conn", None)
            if conn is not None:
                from application.oms.recon_heal_policy import should_auto_repair

                dhan_reconciliation = create_reconciliation_service(
                    orders_adapter=conn.orders,
                    portfolio_adapter=conn.portfolio,
                    oms=svc._trading_context.order_manager,
                    auto_repair=should_auto_repair(),
                )
                # Allow heal path to upsert positions via PositionManager
                svc._trading_context.order_manager.position_manager = (
                    svc._trading_context.position_manager
                )
                svc._trading_context.attach_reconciliation_service(
                    dhan_reconciliation,
                    lifecycle=svc._lifecycle,
                )
        except Exception as exc:
            logger.error("dhan_reconciliation_attach_failed: %s", exc)

    # ------------------------------------------------------------------
    # WebSocket services
    # ------------------------------------------------------------------

    def start_websocket_services(self) -> None:
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
        svc = self._svc
        conn = getattr(svc._gateway, "_conn", None) if svc._gateway else None
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

    # ------------------------------------------------------------------
    # HTTP observability server
    # ------------------------------------------------------------------

    def start_http_observability_server(self, risk_manager) -> None:
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
        from infrastructure.observability.http_server import (
            HttpObservabilityServer,
        )

        svc = self._svc

        # Share the OMS's EventMetrics so /metrics shows the same
        # counters the OMS increments. If the TradingContext is
        # None (init failed), fall back to a fresh EventMetrics.
        event_metrics = None
        if svc._trading_context is not None:
            event_metrics = svc._trading_context.metrics

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
                "risk_fail_open_active": 1.0 if svc._risk_fail_open else 0.0,
            }
            # M-4: extra visibility for ops — capital fallback, drift, DLQ depth,
            # circuit-breaker state, websocket connectivity.
            try:
                gauges["capital_fallback_count"] = float(
                    getattr(svc, "_capital_fallback_count", 0)
                )
            except Exception as exc:
                logger.debug("capital_fallback_gauge_failed: %s", exc)
            ctx = getattr(svc, "_trading_context", None)
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
            conn = getattr(svc._gateway, "_conn", None) if svc._gateway else None
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
                lifecycle=svc._lifecycle,
                event_metrics=event_metrics,
                extra_gauges_fn=_extra_gauges,
            )
            server.start()
            try:
                svc._lifecycle.register(server)
            except Exception as exc:  # pragma: no cover - duplicate name
                logger.debug("http_server_register_failed: %s", exc)
            svc._http_observability = server
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
            svc._http_observability = None
            svc._live_actionable = False
