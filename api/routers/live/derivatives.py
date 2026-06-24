"""Live broker derivatives routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Response

from api.auth import require_auth
from api.deps import get_live_broker_name, require_live_broker
from api.routers.live.headers import apply_live_headers
from api.routers.live.serialize import serialize_value

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/options/chain/{underlying}")
async def live_option_chain(
    underlying: str,
    exchange: str = Query("NFO"),
    expiry: Optional[str] = Query(None),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    if expiry:
        chain = gw.option_chain(underlying, exchange, expiry)
    else:
        chain = gw.option_chain(underlying, exchange)
    return serialize_value(chain)


@router.get("/futures/chain/{underlying}")
async def live_future_chain(
    underlying: str,
    exchange: str = Query("NFO"),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(gw.future_chain(underlying, exchange))
