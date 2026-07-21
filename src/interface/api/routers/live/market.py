"""Live market data routes — domain-object style.

All data access goes through Session → Universe → Instrument.
No broker gateway is referenced directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from domain.constants import DEFAULT_EXCHANGE
from interface.api.auth import require_auth
from interface.api.candle_mapper import series_to_api_candles
from interface.api.routers.live.headers import apply_live_headers
from interface.api.session_state import get_session

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/quote/{symbol}")
async def live_quote(
    symbol: str,
    exchange: str = Query(DEFAULT_EXCHANGE),
    response: Response = None,
) -> dict[str, Any]:
    instrument = get_session().universe.equity(symbol, exchange)
    q = instrument.refresh()
    if q is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quote data for {symbol}",
        )
    if response:
        apply_live_headers(response, "domain")
    # Numeric floats — same contract as /api/v1/market/quote (MoneyField → float).
    return {
        "symbol": symbol,
        "exchange": exchange,
        "ltp": float(q.ltp),
        "open": float(q.open) if q.open is not None else None,
        "high": float(q.high) if q.high is not None else None,
        "low": float(q.low) if q.low is not None else None,
        "close": float(q.close) if q.close is not None else None,
        "volume": float(q.volume) if q.volume is not None else 0.0,
        "change_pct": float(q.change_pct) if q.change_pct is not None else None,
    }


@router.get("/ltp/{symbol}")
async def live_ltp(
    symbol: str,
    exchange: str = Query(DEFAULT_EXCHANGE),
    response: Response = None,
) -> dict[str, Any]:
    instrument = get_session().universe.equity(symbol, exchange)
    q = instrument.refresh()
    ltp = float(q.ltp) if q else 0.0
    if response:
        apply_live_headers(response, "domain")
    return {"symbol": symbol, "exchange": exchange, "ltp": ltp}


@router.get("/depth/{symbol}")
async def live_depth(
    symbol: str,
    exchange: str = Query(DEFAULT_EXCHANGE),
    response: Response = None,
) -> dict[str, Any]:
    instrument = get_session().universe.equity(symbol, exchange)
    d = instrument.depth()
    if response:
        apply_live_headers(response, "domain")
    if d is None:
        return {"symbol": symbol, "bids": [], "asks": []}
    return {
        "symbol": symbol,
        "bids": [{"price": str(b.price), "qty": b.quantity} for b in (d.bids or [])],
        "asks": [{"price": str(a.price), "qty": a.quantity} for a in (d.asks or [])],
    }


@router.get("/candles")
async def live_candles(
    symbol: str = Query(...),
    timeframe: str = Query("1d"),
    days: int = Query(30, ge=1, le=365),
    response: Response = None,
    exchange: str = Query(DEFAULT_EXCHANGE),
) -> dict[str, Any]:
    instrument = get_session().universe.equity(symbol, exchange)
    end = date.today()
    start = end - timedelta(days=days)
    series = instrument.history(timeframe=timeframe, start=start.isoformat(), end=end.isoformat())
    if series.bar_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No candle data for {symbol}/{timeframe}",
        )
    if response:
        apply_live_headers(response, "domain")
    candles = series_to_api_candles(series)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "candles": [c.model_dump() for c in candles],
        "count": len(candles),
    }
