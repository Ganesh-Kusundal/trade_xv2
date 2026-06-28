"""Observability Setup — initializes HTTP observability server with OMS metrics.

Extracted from BrokerService._start_http_observability_server() to reduce
complexity and enable independent testing.

This module handles:
- HTTP observability server creation
- OMS risk state gauge collection
- Broker connectivity metrics
- Reconciliation and DLQ metrics

P-2.4: Port is now configurable via TRADEX_OBSERVABILITY_PORT env var
with automatic fallback to next available port if bind fails.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brokers.common.observability.http_server import HttpObservabilityServer
    from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def _collect_oms_risk_gauges(risk_manager: Any, service: BrokerService) -> dict[str, float]:
    """Collect OMS risk state as Prometheus gauges.

    Args:
        risk_manager: RiskManager instance
        service: BrokerService for fallback count

    Returns:
        Dict of gauge name -> value
    """
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
        "risk_fail_open_active": 1.0 if service._risk_fail_open else 0.0,
    }

    # Capital fallback count
    try:
        gauges["capital_fallback_count"] = float(getattr(service, "_capital_fallback_count", 0))
    except Exception as exc:
        logger.debug("capital_fallback_gauge_failed: %s", exc)

    # Trading context metrics
    ctx = getattr(service, "_trading_context", None)
    if ctx is not None:
        # Dead letter queue
        dlq = getattr(ctx, "dead_letter_queue", None)
        if dlq is not None:
            try:
                gauges["dlq_depth"] = float(len(dlq.entries))
                gauges["dlq_dropped"] = float(getattr(dlq, "dropped", 0))
            except Exception as exc:
                logger.debug("dlq_gauge_failed: %s", exc)

        # Reconciliation metrics
        recon = getattr(ctx, "_reconciliation_service", None)
        if recon is not None:
            try:
                gauges["reconciliation_drift_count"] = float(recon.last_drift_count)
                gauges["reconciliation_run_count"] = float(recon.run_count)
            except Exception as exc:
                logger.debug("reconciliation_gauge_failed: %s", exc)

        # Event log replay count
        if getattr(ctx, "_event_log", None) is not None:
            gauges["event_log_replay_count"] = float(getattr(ctx._event_log, "replay_count", 0))

    # Broker gateway metrics
    if service._gateway is not None:
        try:
            # Connection status
            conn_status = service._gateway.get_connection_status()
            gauges["market_stream_connected"] = (
                1.0 if conn_status.get("market_feed", False) else 0.0
            )
            gauges["order_stream_connected"] = (
                1.0 if conn_status.get("order_stream", False) else 0.0
            )

            # Token refresh metrics
            token_metrics = service._gateway.get_token_refresh_metrics()
            gauges["token_refresh_count"] = float(token_metrics.get("refresh_count", 0))
            gauges["token_refresh_last_error"] = float(token_metrics.get("error_count", 0))

            # Circuit breaker states
            cb_states = service._gateway.get_circuit_breaker_states()
            for name, state_value in cb_states.items():
                gauges[f"cb_{name}"] = float(state_value)
        except Exception as exc:
            logger.debug("gateway_metrics_collection_failed: %s", exc)

    return gauges


def start_http_observability(
    service: BrokerService,
    risk_manager: Any,
) -> HttpObservabilityServer | None:
    """Start HTTP observability server with OMS metrics.

    Constructs an HttpObservabilityServer with:
    - OMS EventMetrics (if TradingContext exists)
    - Extra gauges for OMS risk state, broker connectivity, etc.
    - Lifecycle registration for clean shutdown

    P-2.4: Port is now configurable via TRADEX_OBSERVABILITY_PORT env var.
    If bind fails, automatically tries next available ports (up to 5 attempts).
    Last resort: OS-assigned port (port=0).

    Best-effort: if all ports fail, leaves server as None
    and logs warning. Production observability must not block init.

    Args:
        service: BrokerService instance
        risk_manager: RiskManager instance

    Returns:
        HttpObservabilityServer if started successfully, None otherwise
    """
    from brokers.common.observability.http_server import HttpObservabilityServer

    # Share OMS EventMetrics
    event_metrics = None
    if service._trading_context is not None:
        event_metrics = service._trading_context.metrics

    # Build extra gauges function
    def _extra_gauges() -> dict[str, float]:
        return _collect_oms_risk_gauges(risk_manager, service)

    # P-2.4: Configurable port with fallback
    base_port = int(os.getenv("TRADEX_OBSERVABILITY_PORT", "8765"))

    # Try port, fallback to next available
    for attempt in range(5):
        port = base_port + attempt
        try:
            server = HttpObservabilityServer(
                host="127.0.0.1",
                port=port,
                lifecycle=service._lifecycle,
                event_metrics=event_metrics,
                extra_gauges_fn=_extra_gauges,
            )
            server.start()

            try:
                service._lifecycle.register(server)
            except Exception as exc:  # pragma: no cover - duplicate name
                logger.debug("http_server_register_failed: %s", exc)

            service._http_observability = server
            logger.info(
                "http_observability_started",
                extra={"host": "127.0.0.1", "port": server.port},
            )
            return server

        except OSError:
            # Port in use, try next
            continue

    # Last resort: OS-assigned port
    try:
        server = HttpObservabilityServer(
            host="127.0.0.1",
            port=0,  # OS will assign
            lifecycle=service._lifecycle,
            event_metrics=event_metrics,
            extra_gauges_fn=_extra_gauges,
        )
        server.start()

        try:
            service._lifecycle.register(server)
        except Exception as exc:
            logger.debug("http_server_register_failed: %s", exc)

        service._http_observability = server
        logger.warning(
            "http_observability_started_random_port",
            extra={"host": "127.0.0.1", "port": server.port},
        )
        return server

    except Exception as exc:
        logger.warning("http_observability_start_failed: %s", exc)
        service._http_observability = None
        return None
