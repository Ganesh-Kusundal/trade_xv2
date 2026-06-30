"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from starlette.responses import PlainTextResponse

from api.schemas import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Liveness probe")
async def health_check():
    """Check if the API server is alive.

    Returns 200 OK if the process is running.
    Uses the centralized health registry for component-level checks.
    """
    from infrastructure.health import health_registry as registry

    results = await registry.run_all()
    summary = registry.summary(results)

    return HealthResponse(
        status=summary["status"],
        version="1.0.0",
        timestamp=datetime.now(),
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness_check():
    """Check if the API server is ready to serve traffic.

    Verifies container services and, when live broker intent is set,
    production readiness checks aligned with the CLI live path.
    Returns 503 if any critical service is unavailable.
    """
    from api.deps import get_container

    checks = {}
    all_ready = False

    try:
        container = get_container()
        checks["datalake_gateway"] = container.datalake_gateway is not None
        checks["view_manager"] = container.view_manager is not None
        checks["data_catalog"] = container.data_catalog is not None
        checks["event_bus"] = container.event_bus is not None
        all_ready = all(checks.values())

        broker_service = getattr(container, "broker_service", None)
        live_intent = broker_service is not None and getattr(broker_service, "_live_intent", False)
        if live_intent and broker_service is not None:
            from brokers.common.services.production_readiness import (
                ProductionReadinessChecker,
            )

            report = ProductionReadinessChecker(broker_service).run()
            checks["production_readiness"] = report.passed
            checks["production_readiness_summary"] = report.summary()
            if not report.passed:
                checks["production_readiness_failed"] = report.failed
            all_ready = all_ready and report.passed
        elif broker_service is not None:
            checks["live_broker"] = getattr(broker_service, "live_actionable", False)

        if not all_ready:
            failed = [k for k, v in checks.items() if v is False]
            logger.warning("Readiness check failed: %s", failed)

    except Exception as exc:
        logger.exception("Readiness check failed with exception")
        checks["error"] = str(exc)
        checks["container_initialized"] = False
        all_ready = False

    if not all_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "ready": False,
                "checks": checks,
                "message": "Service not ready for traffic",
            },
        )

    return ReadinessResponse(
        ready=all_ready,
        checks=checks,
        timestamp=datetime.now(),
    )


@router.get("/metrics", response_model=dict)
async def get_metrics():
    """Get observability metrics as JSON.

    Returns HTTP request metrics (always available).
    If OMS is initialized, also includes event metrics, DLQ stats,
    and processed trade stats. Includes cache hit rate and size.
    """
    from api.middleware import http_metrics

    result: dict = {"http_requests": http_metrics.snapshot()}

    try:
        from api.deps import get_container

        ctx = get_container().trading_context
        if ctx is not None:
            result["event_metrics"] = ctx.metrics.snapshot()
            result["dead_letter_queue"] = ctx.dead_letter_queue.stats()
            result["processed_trades"] = ctx.processed_trade_repository.stats()
    except Exception:
        logger.debug("OMS metrics unavailable — returning HTTP metrics only")

    try:
        from infrastructure.metrics import metrics_registry

        snap = metrics_registry.snapshot_detailed()
        cache_info = {}
        for name in ("cache_hits_total", "cache_misses_total", "cache_evictions_total", "cache_size"):
            if name in snap.get("counters", {}):
                cache_info[name] = snap["counters"][name]["value"]
            elif name in snap.get("gauges", {}):
                cache_info[name] = snap["gauges"][name]["value"]
        if cache_info:
            total = cache_info.get("cache_hits_total", 0) + cache_info.get("cache_misses_total", 0)
            cache_info["hit_rate"] = round(cache_info.get("cache_hits_total", 0) / total, 4) if total > 0 else 0
            result["cache"] = cache_info
    except Exception:  # noqa: S110
        pass

    return result


@router.get("/metrics/prometheus")
async def get_metrics_prometheus():
    """Prometheus text exposition format for HTTP request metrics.

    This endpoint is unauthenticated and returns ``text/plain``.
    Useful for Prometheus scrapers and Grafana data sources.
    Combines HTTP request metrics with infrastructure metrics.
    """
    from api.middleware import http_metrics
    from infrastructure.metrics.prometheus import PrometheusExporter

    body = http_metrics.render_prometheus()
    try:
        exporter = PrometheusExporter()
        infra_metrics = exporter.generate()
        body += "\n" + infra_metrics
    except Exception:
        logger.debug("Infrastructure metrics unavailable")
    return PlainTextResponse(content=body, media_type="text/plain")
