"""Dhan segment mapper — mirrors Trade_J's DhanSegmentMapper.java exactly.

All Dhan adapter classes must route ExchangeSegment ↔ wire-value translation
through this module so future Dhan wire-code drift can be patched in one place.
"""

from __future__ import annotations

from brokers.common.core.enums import ExchangeSegment

# CSV segment mapping: "<EXCHANGE_ID>::<SEGMENT_CODE>" → ExchangeSegment
# Mirrors Trade_J's CSV_SEGMENT_TO_INTERNAL map, plus the four extra combinations
# that the Dhan master actually publishes (currency derivatives on NSE/BSE
# and MCX-on-NSE/BSE options under the "M" segment code).
_CSV_TO_INTERNAL: dict[str, ExchangeSegment] = {
    "NSE::E": ExchangeSegment.NSE,  # NSE Equity
    "NSE::D": ExchangeSegment.NSE_FNO,  # NSE Futures & Options
    "NSE::I": ExchangeSegment.IDX_I,  # NSE Index
    "NSE::C": ExchangeSegment.NSE_CURRENCY,  # NSE Currency Derivatives
    "NSE::M": ExchangeSegment.MCX,  # MCX commodity options listed on NSE
    "BSE::E": ExchangeSegment.BSE,  # BSE Equity
    "BSE::D": ExchangeSegment.BSE_FNO,  # BSE Futures & Options
    "BSE::I": ExchangeSegment.IDX_I,  # BSE Index (same enum, IDX_I)
    "BSE::C": ExchangeSegment.BSE_CURRENCY,  # BSE Currency Derivatives
    "BSE::M": ExchangeSegment.MCX,  # MCX commodity options listed on BSE
    "MCX::M": ExchangeSegment.MCX,  # MCX Commodity
    "CDS::D": ExchangeSegment.NSE_CURRENCY,  # Currency Derivatives (legacy "CDS")
}

# Value mapping: string value → ExchangeSegment
# Accepts both Dhan wire values (IDX_I, NSE_FNO) and canonical aliases (NFO, NSE, etc.)
# Mirrors Trade_J's VALUE_TO_INTERNAL map
_VALUE_TO_INTERNAL: dict[str, ExchangeSegment] = {
    "NSE": ExchangeSegment.NSE,
    "NSE_EQ": ExchangeSegment.NSE,
    "BSE": ExchangeSegment.BSE,
    "BSE_EQ": ExchangeSegment.BSE,
    "NFO": ExchangeSegment.NSE_FNO,
    "NSE_FNO": ExchangeSegment.NSE_FNO,
    "BFO": ExchangeSegment.BSE_FNO,
    "BSE_FNO": ExchangeSegment.BSE_FNO,
    "INDEX": ExchangeSegment.IDX_I,
    "IDX_I": ExchangeSegment.IDX_I,
    "IDX": ExchangeSegment.IDX_I,
    "MCX": ExchangeSegment.MCX,
    "MCX_COMM": ExchangeSegment.MCX,
    "CDS": ExchangeSegment.NSE_CURRENCY,
    "NSE_CURRENCY": ExchangeSegment.NSE_CURRENCY,
    "BSE_CURRENCY": ExchangeSegment.BSE_CURRENCY,
}

# Internal → Dhan REST wire value
# These are the exact strings Dhan v2 API accepts for UnderlyingSeg / exchangeSegment
# Mirrors Trade_J's INTERNAL_TO_WIRE map
_INTERNAL_TO_WIRE: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: "NSE_EQ",
    ExchangeSegment.BSE: "BSE_EQ",
    ExchangeSegment.NSE_FNO: "NSE_FNO",
    ExchangeSegment.BSE_FNO: "BSE_FNO",
    ExchangeSegment.IDX_I: "IDX_I",
    ExchangeSegment.MCX: "MCX_COMM",
    ExchangeSegment.NSE_CURRENCY: "NSE_CURRENCY",
    ExchangeSegment.BSE_CURRENCY: "BSE_CURRENCY",
}


def from_csv(exchange_id: str, segment_code: str) -> ExchangeSegment | None:
    """Resolve segment from CSV master columns (SEM_EXM_EXCH_ID + SEM_SEGMENT).

    Example: from_csv("NSE", "D") → ExchangeSegment.NSE_FNO
    Returns None for unknown combinations.
    """
    key = f"{exchange_id.strip().upper()}::{segment_code.strip().upper()}"
    return _CSV_TO_INTERNAL.get(key)


def from_value(value: str) -> ExchangeSegment | None:
    """Resolve segment from any string representation.

    Accepts Dhan wire values (IDX_I, NSE_FNO, MCX_COMM),
    canonical aliases (NFO, NSE, MCX) and index aliases (IDX, INDEX).

    Returns None for unknown values.
    """
    if not value:
        return None
    return _VALUE_TO_INTERNAL.get(value.strip().upper())


_CANONICAL_EXCHANGE: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: "NSE",
    ExchangeSegment.BSE: "BSE",
    ExchangeSegment.NSE_FNO: "NFO",
    ExchangeSegment.BSE_FNO: "BFO",
    ExchangeSegment.IDX_I: "INDEX",
    ExchangeSegment.MCX: "MCX",
    ExchangeSegment.NSE_CURRENCY: "CDS",
    ExchangeSegment.BSE_CURRENCY: "BSE",
}


def to_canonical_exchange(segment: ExchangeSegment) -> str:
    """Map a canonical segment enum to a user-facing exchange label."""
    return _CANONICAL_EXCHANGE.get(segment, segment.value)


def to_wire_value(segment: ExchangeSegment) -> str:
    """Return the Dhan REST API wire value for a canonical ExchangeSegment.

    This is the string sent as ``UnderlyingSeg`` / ``exchangeSegment`` in
    all Dhan v2 REST requests.

    Raises:
        ValueError: if the segment has no Dhan REST mapping.
    """
    wire = _INTERNAL_TO_WIRE.get(segment)
    if wire is None:
        raise ValueError(f"No Dhan REST wire code for segment: {segment!r}")
    return wire
