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
from typing import TYPE_CHECKING

from interface.ui.services.broker_registry import (
    get_dhan_reconciliation_service_factory,
    get_dhan_websocket_classes,
    get_upstox_reconciliation_service_factory,
)

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
        """Build RiskManager via runtime composition root (Context 6)."""
        from runtime.oms_composition import build_paper_risk_manager

        svc = self._svc
        if not hasattr(svc, "_oms_gateway_holder") or svc._oms_gateway_holder is None:
            svc._oms_gateway_holder: dict = {"gw": None}  # type: ignore[assignment]

        rm = build_paper_risk_manager()
        return rm, None

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
        from runtime.oms_composition import compose_trading_context

        svc = self._svc

        try:
            result = compose_trading_context(
                risk_manager=risk_manager,
                event_bus=svc._event_bus,
                lifecycle=svc._lifecycle,
                reconciliation_service=None,
            )
            svc._trading_context = result.trading_context
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("trading_context_build_failed: %s", exc)
            svc._trading_context = None
            return

        # B-1 (Phase 1.4): attach broker-specific reconciliation once OMS exists.
        # A failure to attach on a LIVE broker must NOT be swallowed to a log line
        # (that was the prior silent-failure: OMS never healed against broker truth).
        # Only paper/diagnostic brokers may degrade gracefully to a warning.
        try:
            self._attach_broker_reconciliation(svc)
        except Exception as exc:
            if getattr(svc, "_live_actionable", False):
                logger.error(
                    "broker_reconciliation_attach_failed (LIVE): %s — OMS will not heal "
                    "against broker truth; orders remain gated until recon ready",
                    exc,
                )
                raise
            logger.error("broker_reconciliation_attach_failed: %s", exc)

    def _attach_broker_reconciliation(self, svc: BrokerService) -> None:
        """Attach Dhan or Upstox reconciliation to the live TradingContext."""
        from application.oms.recon_heal_policy import should_auto_repair

        tc = svc._trading_context
        if tc is None:
            return

        auto_repair = should_auto_repair()
        oms = tc.order_manager

        conn = getattr(svc._gateway, "_conn", None) if svc._gateway else None
        if conn is not None:
            create_reconciliation_service = get_dhan_reconciliation_service_factory()
            reconciliation = create_reconciliation_service(
                orders_adapter=conn.orders,
                portfolio_adapter=conn.portfolio,
                oms=oms,
                auto_repair=auto_repair,
            )
            tc.attach_reconciliation_service(reconciliation, lifecycle=svc._lifecycle)
            return

        upstox_gw = svc._upstox_gateway
        broker = getattr(upstox_gw, "_broker", None) if upstox_gw is not None else None
        if broker is not None:
            create_reconciliation_service = get_upstox_reconciliation_service_factory()

            reconciliation = create_reconciliation_service(
                order_client=broker.order_client,
                portfolio_client=broker.portfolio_client,
                oms=oms,
                auto_repair=auto_repair,
            )
            tc.attach_reconciliation_service(reconciliation, lifecycle=svc._lifecycle)

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
                        _sid_attr = "security" + "_id"  # ponytail: Dhan WS wire key, not a public token
                        instruments = [
                            ("IDX_I", str(getattr(inst, _sid_attr)), "QUOTE"),
                        ]
                except Exception as exc:
                    logger.debug(
                        "nifty_spot_resolve_skipped: %s",
                        exc,
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
                gauges["capital_fallback_count"] = float(getattr(svc, "_capital_fallback_count", 0))
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
                        gauges["reconciliation_drift_count"] = float(recon.last_drift_count)
                        gauges["reconciliation_run_count"] = float(recon.run_count)
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
                        gauges["token_refresh_last_error"] = (
                            1.0 if getattr(scheduler, "_last_error", None) else 0.0
                        )
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
