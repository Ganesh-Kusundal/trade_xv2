"""Live broker portfolio routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from api.auth import require_auth
from api.deps import get_live_broker_name, require_live_broker
from api.routers.live.headers import apply_live_headers
from api.routers.live.serialize import serialize_value

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/positions")
async def live_positions(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return {"positions": serialize_value(gw.positions())}


@router.get("/holdings")
async def live_holdings(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return {"holdings": serialize_value(gw.holdings())}


@router.get("/funds")
async def live_funds(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(gw.funds())
