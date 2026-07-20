"""Segment-aware instrument resolver.

Maps a CLI ``segment`` name to the correct :class:`~domain.universe.Universe`
factory with the right default exchange, replacing the scattered string-exchange
heuristics in ``commands/market.py`` (``resolve_exchange``).  Pure and
unit-testable — no broker, gateway, or rich dependency.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument
    from domain.universe import Session

# segment -> (Universe factory attr, default exchange)
_SEGMENTS: dict[str, dict[str, str]] = {
    "equity": {"factory": "equity", "exchange": "NSE"},
    "etf": {"factory": "etf", "exchange": "NSE"},
    "spot": {"factory": "spot", "exchange": "NSE"},
    "currency": {"factory": "currency", "exchange": "NSE"},
    "index": {"factory": "index", "exchange": "NSE"},
    "future": {"factory": "future", "exchange": "NFO"},
    "commodity": {"factory": "commodity", "exchange": "MCX"},
    "options": {"factory": "option", "exchange": "NFO"},
}


def list_segments() -> list[str]:
    """Known segment names (sorted)."""
    return sorted(_SEGMENTS)


def default_exchange(segment: str) -> str:
    """Default exchange code for *segment* (raises on unknown)."""
    seg = _SEGMENTS.get(segment.lower())
    if seg is None:
        raise ValueError(f"Unknown segment: {segment!r}. Known: {list_segments()}")
    return seg["exchange"]


def resolve_instrument(
    session: Session,
    segment: str,
    symbol: str,
    *,
    expiry: date | str | None = None,
    strike: Decimal | float | int | None = None,
    right: str | None = None,
    exchange: str | None = None,
) -> Instrument:
    """Resolve a broker-bound :class:`Instrument` for *segment* + *symbol*.

    Segments needing extra args:
        - ``future`` / ``commodity``: ``expiry`` required.
        - ``options``: ``expiry`` + ``strike`` + ``right`` required for a
          concrete option; otherwise (underlying only) an index-like instrument
          is returned so ``.option_chain()`` works.
    """
    seg_key = segment.lower()
    seg = _SEGMENTS.get(seg_key)
    if seg is None:
        raise ValueError(f"Unknown segment: {segment!r}. Known: {list_segments()}")

    exch = (exchange or seg["exchange"]).upper()
    factory = getattr(session.universe, seg["factory"])

    if seg_key in ("future", "commodity"):
        if expiry is None:
            raise ValueError(f"segment '{segment}' requires --expiry <YYYY-MM-DD>")
        return factory(symbol, expiry=_coerce_date(expiry), exchange=exch)

    if seg_key == "options":
        # Concrete option (flag form).
        if strike is not None and right is not None and expiry is not None:
            return factory(
                symbol,
                strike=_coerce_decimal(strike),
                right=str(right).upper(),
                expiry=_coerce_date(expiry),
                exchange=exch,
            )
        # Underlying only -> resolve as index-like for the chain.
        return session.universe.index(symbol, exchange=exch)

    # equity / etf / spot / currency / index
    return factory(symbol, exchange=exch)


def _coerce_date(v: date | str) -> date:
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d").date()
    return datetime.strptime(s, "%Y%m%d").date()


def _coerce_decimal(v: Decimal | float | int) -> Decimal:
    from decimal import Decimal as D

    return D(str(v))
