"""Live market data routes — domain-object style.

All data access goes through Session → Universe → Instrument.
No broker gateway is referenced directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from api.auth import require_auth
from api.routers.live.headers import apply_live_headers
from domain.universe import Session

router = APIRouter(dependencies=[Depends(require_auth)])

# ── Session DI ──────────────────────────────────────────────────────
_session: Session | None = None


def set_session(session: Session) -> None:
    global _session
    _session = session


def _get_session() -> Session:
    if _session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session not wired — call set_session() at startup",
        )
    return _session


@router.get("/quote/{symbol}")
async def live_quote(
    symbol: str,
    exchange: str = Query("NSE"),
    response: Response = None,
) -> dict[str, Any]:
    instrument = _get_session().universe.equity(symbol, exchange)
    q = instrument.refresh()
    if q is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No quote data for {symbol}",
        )
    if response:
        apply_live_headers(response, "domain")
    return {
        "symbol": symbol,
        "exchange": exchange,
        "ltp": str(q.ltp),
        "open": str(q.open),
        "high": str(q.high),
        "low": str(q.low),
        "close": str(q.close),
        "volume": q.volume,
        "change_pct": str(q.change_pct),
    }


@router.get("/ltp/{symbol}")
async def live_ltp(
    symbol: str,
    exchange: str = Query("NSE"),
    response: Response = None,
) -> dict[str, Any]:
    instrument = _get_session().universe.equity(symbol, exchange)
    q = instrument.refresh()
    ltp = str(q.ltp) if q else "0"
    if response:
        apply_live_headers(response, "domain")
    return {"symbol": symbol, "exchange": exchange, "ltp": ltp}


@router.get("/depth/{symbol}")
async def live_depth(
    symbol: str,
    exchange: str = Query("NSE"),
    response: Response = None,
) -> dict[str, Any]:
    instrument = _get_session().universe.equity(symbol, exchange)
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
    exchange: str = Query("NSE"),
) -> dict[str, Any]:
    instrument = _get_session().universe.equity(symbol, exchange)
    end = date.today()
    start = end - timedelta(days=days)
    df = instrument.history(timeframe=timeframe, start=start.isoformat(), end=end.isoformat())
    if response:
        apply_live_headers(response, "domain")
    rows = df.to_dict(orient="records") if not df.empty else []
    return {"symbol": symbol, "timeframe": timeframe, "candles": rows}
