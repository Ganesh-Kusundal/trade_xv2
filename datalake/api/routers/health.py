"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.responses import PlainTextResponse

from datalake.api.deps import get_trading_context
from datalake.api.schemas import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=HealthResponse, summary="Liveness probe")
async def health_check():
    """Check if the API server is alive.
    
    Returns 200 OK if the process is running.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(),
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness_check():
    """Check if the API server is ready to serve traffic.
    
    Verifies that all required services are initialized.
    Returns 503 if any critical service is unavailable.
    """
    from datalake.api.deps import get_container
    
    checks = {}
    all_ready = False
    
    try:
        container = get_container()
        checks["datalake_gateway"] = container.datalake_gateway is not None
        checks["view_manager"] = container.view_manager is not None
        checks["data_catalog"] = container.data_catalog is not None
        checks["event_bus"] = container.event_bus is not None
        all_ready = all(checks.values())
        
        if not all_ready:
            failed = [k for k, v in checks.items() if not v]
            logger.warning("Readiness check failed: services not ready: %s", failed)
            
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
    and processed trade stats.
    """
    from datalake.api.middleware import http_metrics
    result: dict = {"http_requests": http_metrics.snapshot()}

    try:
        from datalake.api.deps import get_container
        ctx = get_container().trading_context
        if ctx is not None:
            result["event_metrics"] = ctx.metrics.snapshot()
            result["dead_letter_queue"] = ctx.dead_letter_queue.stats()
            result["processed_trades"] = ctx.processed_trade_repository.stats()
    except Exception:
        logger.debug("OMS metrics unavailable — returning HTTP metrics only")

    return result


@router.get("/metrics/prometheus")
async def get_metrics_prometheus():
    """Prometheus text exposition format for HTTP request metrics.

    This endpoint is unauthenticated and returns ``text/plain``.
    Useful for Prometheus scrapers and Grafana data sources.
    """
    from datalake.api.middleware import http_metrics
    body = http_metrics.render_prometheus()
    return PlainTextResponse(content=body, media_type="text/plain")
