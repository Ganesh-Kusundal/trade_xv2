"""Broker-agnostic index symbol mapping for v2 plugins.

Ported from ``src/config/indices.py`` — single source of truth for resolving
bare index symbols (NIFTY, BANKNIFTY, SENSEX, …) to broker-specific exchange,
segment, and security-ID values.

Both Dhan and Upstox resolve indices differently from equities:

* **Dhan**: Indices use exchange ``"INDEX"`` and segment ``"IDX_I"``.
* **Upstox**: Indices use segment ``"NSE_INDEX"`` (or ``"BSE_INDEX"``).

This module provides:

* :data:`INDEX_SYMBOLS` — a frozen set of all known index symbols.
* :func:`is_index` — fast membership check.
* :func:`get_index_entry` — return the full entry for a symbol.
* :func:`dhan_index_exchange` / :func:`dhan_index_segment` — Dhan helpers.
* :func:`upstox_index_segment` — Upstox segment helper.
* :func:`index_upstox_key` — full Upstox instrument_key for an index.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects import InstrumentId


@dataclass(frozen=True)
class _IndexEntry:
    """Broker-agnostic index metadata."""

    canonical_name: str
    dhan_exchange: str = "INDEX"
    dhan_segment: str = "IDX_I"
    dhan_security_id: str | None = None
    upstox_segment: str = ""
    upstox_name: str = ""


# ── Master index registry ────────────────────────────────────────────────────

_INDEX_MAP: dict[str, _IndexEntry] = {
    # ── NSE indices ──────────────────────────────────────────────────────
    "NIFTY": _IndexEntry(
        canonical_name="NIFTY 50",
        dhan_security_id="13",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 50",
    ),
    "NIFTY50": _IndexEntry(
        canonical_name="NIFTY 50",
        dhan_security_id="13",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 50",
    ),
    "BANKNIFTY": _IndexEntry(
        canonical_name="NIFTY BANK",
        dhan_security_id="25",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Bank",
    ),
    "NIFTYBANK": _IndexEntry(
        canonical_name="NIFTY BANK",
        dhan_security_id="25",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Bank",
    ),
    "FINNIFTY": _IndexEntry(
        canonical_name="NIFTY FINANCIAL SERVICES",
        dhan_security_id="27",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Fin Service",
    ),
    "NIFTYFIN": _IndexEntry(
        canonical_name="NIFTY FINANCIAL SERVICES",
        dhan_security_id="27",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Fin Service",
    ),
    "MIDCAPNIFTY": _IndexEntry(
        canonical_name="NIFTY MIDCAP 100",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Midcap 100",
    ),
    "NIFTYMIDCAP": _IndexEntry(
        canonical_name="NIFTY MIDCAP 100",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Midcap 100",
    ),
    "NIFTYIT": _IndexEntry(
        canonical_name="NIFTY IT",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty IT",
    ),
    "NIFTYPHARMA": _IndexEntry(
        canonical_name="NIFTY PHARMA",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Pharma",
    ),
    "NIFTYAUTO": _IndexEntry(
        canonical_name="NIFTY AUTO",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Auto",
    ),
    "NIFTYFMCG": _IndexEntry(
        canonical_name="NIFTY FMCG",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty FMCG",
    ),
    "NIFTYMETAL": _IndexEntry(
        canonical_name="NIFTY METAL",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Metal",
    ),
    "NIFTYREALTY": _IndexEntry(
        canonical_name="NIFTY REALTY",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Realty",
    ),
    "NIFTYENERGY": _IndexEntry(
        canonical_name="NIFTY ENERGY",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Energy",
    ),
    "NIFTYMEDIA": _IndexEntry(
        canonical_name="NIFTY MEDIA",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Media",
    ),
    "NIFTYPSB": _IndexEntry(
        canonical_name="NIFTY PSU BANK",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty PSU Bank",
    ),
    "NIFTYPVTBANK": _IndexEntry(
        canonical_name="NIFTY PRIVATE BANK",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Pvt Bank",
    ),
    "NIFTYCONS": _IndexEntry(
        canonical_name="NIFTY CONSUMER DURABLES",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Consumer Durables",
    ),
    "NIFTYOILGAS": _IndexEntry(
        canonical_name="NIFTY OIL AND GAS",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Oil and Gas",
    ),
    "NIFTYCOMM": _IndexEntry(
        canonical_name="NIFTY COMMODITIES",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Commodities",
    ),
    "NIFTYIND": _IndexEntry(
        canonical_name="NIFTY INDUSTRIALS",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Industrials",
    ),
    "NIFTYMNC": _IndexEntry(
        canonical_name="NIFTY MNC",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty MNC",
    ),
    "NIFTYSMALL": _IndexEntry(
        canonical_name="NIFTY SMALLCAP 250",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Smallcap 250",
    ),
    "NIFTYMICRO": _IndexEntry(
        canonical_name="NIFTY MICROCAP 250",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Microcap 250",
    ),
    "NIFTYNEXT50": _IndexEntry(
        canonical_name="NIFTY NEXT 50",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Next 50",
    ),
    "NIFTY100": _IndexEntry(
        canonical_name="NIFTY 100",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 100",
    ),
    "NIFTY200": _IndexEntry(
        canonical_name="NIFTY 200",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 200",
    ),
    "NIFTY500": _IndexEntry(
        canonical_name="NIFTY 500",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 500",
    ),
    "VXNIFTY": _IndexEntry(
        canonical_name="NIFTY VOLATILITY",
        upstox_segment="NSE_INDEX",
        upstox_name="India VIX",
    ),
    "INDIAVIX": _IndexEntry(
        canonical_name="INDIA VIX",
        upstox_segment="NSE_INDEX",
        upstox_name="India VIX",
    ),
    # ── BSE indices ──────────────────────────────────────────────────────
    "SENSEX": _IndexEntry(
        canonical_name="SENSEX",
        upstox_segment="BSE_INDEX",
        upstox_name="SENSEX",
    ),
    "BSESENSEX": _IndexEntry(
        canonical_name="SENSEX",
        upstox_segment="BSE_INDEX",
        upstox_name="SENSEX",
    ),
    "BSE100": _IndexEntry(
        canonical_name="BSE 100",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 100",
    ),
    "BSE500": _IndexEntry(
        canonical_name="BSE 500",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 500",
    ),
    "BSEMIDCAP": _IndexEntry(
        canonical_name="BSE MIDCAP",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE Midcap",
    ),
    "BSESMALLCAP": _IndexEntry(
        canonical_name="BSE SMALLCAP",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE Smallcap",
    ),
    # ── Global indices (Upstox only) ─────────────────────────────────────
    "DOW": _IndexEntry(
        canonical_name="DOW JONES",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="DOW JONES",
    ),
    "NASDAQ": _IndexEntry(
        canonical_name="NASDAQ",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="NASDAQ",
    ),
    "S&P500": _IndexEntry(
        canonical_name="S&P 500",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="S&P 500",
    ),
}

INDEX_SYMBOLS: frozenset[str] = frozenset(_INDEX_MAP.keys())

# ── F&O exchange mapping ─────────────────────────────────────────────────────
INDEX_TO_FNO_EXCHANGE: dict[str, str] = {
    "NIFTY": "NFO",
    "BANKNIFTY": "NFO",
    "FINNIFTY": "NFO",
    "SENSEX": "BFO",
}


def _normalize(symbol: str) -> str:
    return symbol.upper().strip()


def is_index(symbol: str) -> bool:
    """Check if *symbol* is a known index (case-insensitive)."""
    return _normalize(symbol) in INDEX_SYMBOLS


def is_pure_index(instrument_id: "InstrumentId") -> bool:
    """True only when *instrument_id* is the spot index itself (not a derivative
    on an index).

    A derivative whose *underlying* happens to be an index (``NFO:NIFTY:...:FUT``,
    ``BFO:SENSEX``) must NOT be treated as the index — it trades in the F&O
    segment, not ``IDX_I``. The pure index is identified by: exchange
    ``IDX``/``INDEX``, or exchange ``NSE``/``BSE`` with an index underlying and
    no expiry/strike/right qualifier.
    """
    exch = instrument_id.exchange
    if exch in ("IDX", "INDEX"):
        return True
    if exch in ("NSE", "BSE") and is_index(instrument_id.underlying):
        return instrument_id.expiry is None and instrument_id.strike is None and instrument_id.right is None
    return False


def get_index_entry(symbol: str) -> _IndexEntry | None:
    """Return :class:`_IndexEntry` for *symbol*, or ``None`` if not an index."""
    return _INDEX_MAP.get(_normalize(symbol))


def dhan_index_exchange(symbol: str) -> str | None:
    """Return Dhan exchange name (``"INDEX"``) if *symbol* is an index."""
    entry = _INDEX_MAP.get(_normalize(symbol))
    return entry.dhan_exchange if entry else None


def dhan_index_segment(symbol: str) -> str | None:
    """Return Dhan segment (``"IDX_I"``) if *symbol* is an index."""
    entry = _INDEX_MAP.get(_normalize(symbol))
    return entry.dhan_segment if entry else None


def upstox_index_segment(symbol: str) -> str | None:
    """Return Upstox segment (e.g. ``"NSE_INDEX"``) if *symbol* is an index."""
    entry = _INDEX_MAP.get(_normalize(symbol))
    return entry.upstox_segment if entry else None


def index_upstox_key(symbol: str) -> str | None:
    """Return the Upstox instrument_key for *symbol*."""
    entry = _INDEX_MAP.get(_normalize(symbol))
    if entry and entry.upstox_segment and entry.upstox_name:
        return f"{entry.upstox_segment}|{entry.upstox_name}"
    return None


def list_indices() -> list[dict[str, str]]:
    """Return a human-readable list of all registered indices."""
    return [
        {
            "symbol": sym,
            "name": entry.canonical_name,
            "dhan_exchange": entry.dhan_exchange,
            "upstox_segment": entry.upstox_segment,
        }
        for sym, entry in sorted(_INDEX_MAP.items())
    ]
