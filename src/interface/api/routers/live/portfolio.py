"""Live broker portfolio routes — domain AccountView, not wire gateway."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from interface.api.auth import require_auth
from interface.api.deps import get_broker_service, get_live_broker_name
from interface.api.routers.live.headers import apply_live_headers
from interface.api.routers.live.serialize import serialize_value

router = APIRouter(dependencies=[Depends(require_auth)])


def _account_snapshot() -> Any:
    """Refresh portfolio via domain session (positions/holdings/funds)."""
    svc = get_broker_service()
    if svc is None or getattr(svc, "active_broker", None) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live broker not configured",
            headers={"Retry-After": "30"},
        )
    from application.portfolio.active_session import get_active_session, refresh_account

    session = get_active_session(svc)
    try:
        return refresh_account(session)
    finally:
        session.close()


@router.get("/positions")
async def live_positions(response: Response = None) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    acct = _account_snapshot()
    return {"positions": serialize_value(acct.positions)}


@router.get("/holdings")
async def live_holdings(response: Response = None) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    acct = _account_snapshot()
    return {"holdings": serialize_value(acct.holdings)}


@router.get("/funds")
async def live_funds(response: Response = None) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    acct = _account_snapshot()
    return serialize_value(acct.funds)
