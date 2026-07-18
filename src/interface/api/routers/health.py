"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from starlette.responses import PlainTextResponse

from interface.api.schemas import HealthResponse, ReadinessResponse

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
        timestamp=datetime.now(timezone.utc),
    )


async def _readiness_probe() -> ReadinessResponse:
    """Shared readiness logic for ``/readyz`` and ``/ready``."""
    from application.services.api_readiness import evaluate_api_readiness
    from interface.api.deps import get_container

    try:
        container = get_container()
        report = evaluate_api_readiness(container)
    except Exception as exc:
        logger.exception("Readiness check failed with exception")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "ready": False,
                "checks": [{"id": "container", "status": "failed", "message": str(exc)}],
                "message": "Service not ready for traffic",
            },
        ) from exc

    if not report.ready:
        failed = [c.id for c in report.checks if c.status != "passed"]
        logger.warning("Readiness check failed: %s", failed)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "ready": False,
                "checks": report.to_dict()["checks"],
                "message": "Service not ready for traffic",
            },
        )

    return ReadinessResponse(
        ready=report.ready,
        checks=report.as_bool_map(),
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness_check():
    """Check if the API server is ready to serve traffic.

    Verifies event bus, OMS context, reconciliation gate, and broker session.
    Returns 503 if any critical gate is unavailable.
    """
    return await _readiness_probe()


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe (alias)")
async def readiness_alias():
    """Alias for ``/readyz`` (DEVELOPER-PLATFORM §health endpoints)."""
    return await _readiness_probe()


@router.get("/metrics", response_model=dict)
async def get_metrics():
    """Get observability metrics as JSON.

    Returns HTTP request metrics (always available).
    If OMS is initialized, also includes event metrics, DLQ stats,
    and processed trade stats. Includes cache hit rate and size.
    """
    from interface.api.middleware import http_metrics

    result: dict = {"http_requests": http_metrics.snapshot()}

    try:
        from interface.api.deps import get_container

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
    except Exception:
        pass

    return result


@router.get("/metrics/prometheus")
async def get_metrics_prometheus():
    """Prometheus text exposition format for HTTP request metrics.

    This endpoint is unauthenticated and returns ``text/plain``.
    Useful for Prometheus scrapers and Grafana data sources.
    """
    from interface.api.middleware import http_metrics

    body = http_metrics.render_prometheus()
    return PlainTextResponse(content=body, media_type="text/plain")
