"""Instrument lookup services — resolve symbols to public instrument metadata."""

from __future__ import annotations

from typing import Any

from brokers.session import BrokerSession

from ._session import _borrow_session


def lookup_instrument(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Resolve symbol → public instrument metadata (no broker tokens)."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        return {
            "symbol": symbol,
            "exchange": inst.exchange,
            "instrument_id": str(inst.id),
            "underlying": getattr(inst.id, "underlying", symbol),
            "tick_size": str(inst.tick_size) if inst.tick_size is not None else None,
            "lot_size": inst.lot_size,
        }
    finally:
        if close:
            s.close()


def lookup_security(
    broker: str, symbol: str, exchange: str = "NSE", **kwargs: Any
) -> dict[str, Any]:
    """Backward-compatible alias for :func:`lookup_instrument`."""
    return lookup_instrument(broker, symbol, exchange=exchange, **kwargs)


def lookup_symbol(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> str:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.instrument_id(symbol, exchange=exchange)
    finally:
        if close:
            s.close()


__all__ = [
    "lookup_instrument",
    "lookup_security",
    "lookup_symbol",
]
