"""Live broker health, readiness, and capability matrix."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.auth import require_auth
from api.deps import get_broker_service, get_live_broker_name, require_live_broker
from api.routers.live.headers import apply_live_headers
from api.routers.live.serialize import serialize_value

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/health")
async def live_health(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    """Broker gateway describe() + token presence."""
    apply_live_headers(response, get_live_broker_name())
    describe = gw.describe() if hasattr(gw, "describe") else {}
    return {
        "status": "healthy",
        "broker": get_live_broker_name(),
        "describe": serialize_value(describe),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/readyz")
async def live_readyz(
    response: Response = None,
    broker_service: Any = Depends(get_broker_service),
) -> dict[str, Any]:
    """Production readiness subset aligned with doctor quick checks."""
    apply_live_headers(response, get_live_broker_name())
    if broker_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker service not configured",
            headers={"Retry-After": "30"},
        )
    try:
        from brokers.common.services.production_readiness import ProductionReadinessChecker

        report = ProductionReadinessChecker(broker_service).run()
        payload = {
            "ready": report.passed,
            "summary": report.summary(),
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in report.checks
            ],
            "timestamp": datetime.now().isoformat(),
        }
        if not report.passed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=payload,
            )
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"ready": False, "error": str(exc)},
        ) from exc


@router.get("/capabilities")
async def live_capabilities(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    """Return gateway.capabilities() matrix."""
    apply_live_headers(response, get_live_broker_name())
    caps = gw.capabilities() if hasattr(gw, "capabilities") else None
    return {
        "broker": get_live_broker_name(),
        "capabilities": serialize_value(caps),
    }
