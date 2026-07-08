"""Domain-object API pattern — the reference implementation for Phase 6.

This module demonstrates how ``api/`` and ``cli/`` consumers should interact
with the domain: through ``Session`` → ``Universe`` → ``Instrument`` objects,
never through broker gateways or manager singletons.

Every endpoint below uses ZERO ``brokers.*`` imports.  The broker is invisible —
it lives behind the ``DataProvider`` / ``ExecutionProvider`` ports wired at
the composition root.

Usage (FastAPI DI)::

    from api.v2.domain_endpoints import router as domain_router
    app.include_router(domain_router, prefix="/v2")

    # Composition root (once, at startup):
    from domain.universe import Session
    from brokers.dhan.transport import DhanTransport
    transport = DhanTransport(gateway)
    session = Session(transport.market_data, event_bus=event_bus)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from domain.instruments.instrument import Equity, Future, Instrument, Option
from domain.universe import Session


# ── DI helpers (composition root) ───────────────────────────────────

_session: Session | None = None


def set_session(session: Session) -> None:
    """Wire the platform-wide Session (called once at startup)."""
    global _session
    _session = session


def get_session() -> Session:
    if _session is None:
        raise RuntimeError("Session not wired — call set_session() at startup")
    return _session


# ── Endpoints (domain-object style) ─────────────────────────────────

router = APIRouter(tags=["domain-v2"])


@router.get("/v2/quote/{symbol}")
async def quote(
    symbol: str,
    exchange: str = Query("NSE"),
    session: Session = Depends(get_session),
) -> dict:
    """Latest quote via domain objects — no broker/gateway in sight."""
    instrument = session.universe.equity(symbol, exchange)
    q = instrument.refresh()
    if q is None:
        return {"symbol": symbol, "ltp": None, "error": "no data"}
    return {
        "symbol": symbol,
        "exchange": exchange,
        "ltp": str(q.ltp),
        "bid": str(q.bid) if q.bid else None,
        "ask": str(q.ask) if q.ask else None,
        "volume": q.volume,
    }


@router.get("/v2/history/{symbol}")
async def history(
    symbol: str,
    timeframe: str = Query("1D"),
    days: int = Query(120, ge=1, le=1000),
    exchange: str = Query("NSE"),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Historical OHLCV via domain objects."""
    instrument = session.universe.equity(symbol, exchange)
    df = instrument.history(timeframe=timeframe, days=days)
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/v2/option-chain/{underlying}")
async def option_chain(
    underlying: str,
    expiry: date | None = Query(None),
    exchange: str = Query("NSE"),
    session: Session = Depends(get_session),
) -> dict:
    """Option chain via domain objects."""
    instrument = session.universe.equity(underlying, exchange)
    chain = instrument.option_chain(expiry)
    return {
        "underlying": chain.underlying,
        "expiry": chain.expiry,
        "spot": str(chain.spot) if chain.spot else None,
        "atm_strike": str(chain.atm.strike) if chain.atm else None,
        "strike_count": len(chain.strikes),
    }


@router.get("/v2/depth/{symbol}")
async def depth(
    symbol: str,
    exchange: str = Query("NSE"),
    session: Session = Depends(get_session),
) -> dict:
    """Market depth via domain objects."""
    instrument = session.universe.equity(symbol, exchange)
    d = instrument.depth()
    if d is None:
        return {"symbol": symbol, "bids": [], "asks": []}
    return {
        "symbol": symbol,
        "bids": [{"price": str(b.price), "qty": b.quantity} for b in (d.bids or [])],
        "asks": [{"price": str(a.price), "qty": a.quantity} for a in (d.asks or [])],
    }


@router.post("/v2/order/{symbol}")
async def place_order(
    symbol: str,
    side: str = Query("BUY"),
    quantity: int = Query(1, ge=1),
    price: Decimal = Query(Decimal("0")),
    order_type: str = Query("MARKET"),
    exchange: str = Query("NSE"),
    session: Session = Depends(get_session),
) -> dict:
    """Place order via domain objects (requires ExecutionProvider wired in Session)."""
    from domain.orders.requests import OrderRequest
    from domain.types import OrderType, ProductType, Side

    instrument = session.universe.equity(symbol, exchange)
    # In a real setup, Session would also expose an ExecutionProvider.
    # Here we demonstrate the pattern; the actual execution wiring
    # requires Transport.execution to be exposed through Session.
    return {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "status": "demo — execution wiring in progress",
    }
