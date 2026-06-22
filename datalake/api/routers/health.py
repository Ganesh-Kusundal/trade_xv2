"""Health and readiness endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from datalake.api.deps import get_trading_context
from datalake.api.schemas import HealthResponse, ReadinessResponse

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
    """
    from datalake.api.deps import get_service
    
    checks = {
        "datalake_gateway": get_service("datalake_gateway", required=False) is not None,
        "view_manager": get_service("view_manager", required=False) is not None,
        "data_catalog": get_service("data_catalog", required=False) is not None,
    }
    
    all_ready = all(checks.values())
    
    return ReadinessResponse(
        ready=all_ready,
        checks=checks,
        timestamp=datetime.now(),
    )


@router.get("/metrics", response_model=dict)
async def get_metrics(ctx=Depends(get_trading_context)):
    """Get OMS observability metrics.
    
    Returns event metrics, dead-letter queue stats, and processed trade repository stats.
    """
    return {
        "event_metrics": ctx.metrics.snapshot(),
        "dead_letter_queue": ctx.dead_letter_queue.stats(),
        "processed_trades": ctx.processed_trade_repository.stats(),
    }
