"""Live broker market data routes."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from api.auth import require_auth
from api.deps import get_live_broker_name, require_live_broker
from api.routers.live.headers import apply_live_headers
from api.routers.live.serialize import serialize_value

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/quote/{symbol}")
async def live_quote(
    symbol: str,
    exchange: str = Query("NSE"),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(gw.quote(symbol, exchange))


@router.get("/ltp/{symbol}")
async def live_ltp(
    symbol: str,
    exchange: str = Query("NSE"),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return {
        "symbol": symbol,
        "exchange": exchange,
        "ltp": serialize_value(gw.ltp(symbol, exchange)),
    }


@router.get("/depth/{symbol}")
async def live_depth(
    symbol: str,
    exchange: str = Query("NSE"),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    return serialize_value(gw.depth(symbol, exchange))


@router.get("/candles")
async def live_candles(
    symbol: str = Query(...),
    timeframe: str = Query("1d"),
    days: int = Query(30, ge=1, le=365),
    response: Response = None,
    gw: Any = Depends(require_live_broker),
) -> dict[str, Any]:
    apply_live_headers(response, get_live_broker_name())
    end = date.today()
    start = end - timedelta(days=days)
    df = gw.history(symbol, timeframe, start, end)
    if df is None:
        rows = []
    elif hasattr(df, "to_dict"):
        rows = df.to_dict(orient="records")
    else:
        rows = list(df)
    return {"symbol": symbol, "timeframe": timeframe, "candles": serialize_value(rows)}
