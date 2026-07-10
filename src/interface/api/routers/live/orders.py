"""Live broker order query routes (read-only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from interface.api.auth import require_auth
from interface.api.deps import get_live_broker_name, require_live_broker
from interface.api.routers.live.headers import apply_live_headers
from interface.api.routers.live.serialize import serialize_value

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/orders")
async def live_orders(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return {"orders": serialize_value(gw.get_orderbook())}


@router.get("/trades")
async def live_trades(
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    trades = gw.get_trade_book() if hasattr(gw, "get_trade_book") else gw.trades()
    return {"trades": serialize_value(trades)}
