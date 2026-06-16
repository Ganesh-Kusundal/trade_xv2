"""Dhan segment code mappings — single source of truth."""

from __future__ import annotations

from brokers.dhan.domain import Exchange

EXCHANGE_TO_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "MCX": "MCX_COMM",
    "CDS": "NSE_CURRENCY",
    "INDEX": "IDX_I",
}

SEGMENT_TO_EXCHANGE: dict[str, str] = {v: k for k, v in EXCHANGE_TO_SEGMENT.items()}
SEGMENT_TO_EXCHANGE.update({
    "BSE_CURRENCY": "CDS",
    "NSE_COMM": "MCX",
})

_COMPACT_SEGMENT_MAP: dict[tuple[str, str], str] = {
    ("NSE", "E"): "NSE_EQ",
    ("NSE", "D"): "NSE_FNO",
    ("NSE", "I"): "IDX_I",
    ("BSE", "E"): "BSE_EQ",
    ("BSE", "D"): "BSE_FNO",
    ("BSE", "I"): "IDX_I",
    ("MCX", "M"): "MCX_COMM",
    ("CDS", "D"): "NSE_CURRENCY",
    ("NSE", "C"): "NSE_CURRENCY",
    ("BSE", "C"): "BSE_CURRENCY",
    ("NSE", "M"): "NSE_COMM",
}

# Binary protocol numeric codes (Dhan v2 websocket)
NUMERIC_TO_SEGMENT: dict[int, str] = {
    0: "IDX_I",
    1: "NSE_EQ",
    2: "NSE_FNO",
    3: "NSE_CURRENCY",
    4: "BSE_EQ",
    5: "MCX_COMM",
    7: "BSE_CURRENCY",
    8: "BSE_FNO",
}

SEGMENT_TO_NUMERIC: dict[str, int] = {v: k for k, v in NUMERIC_TO_SEGMENT.items()}


def segment_to_exchange(segment: str, default: str = "NSE") -> Exchange:
    exch_str = SEGMENT_TO_EXCHANGE.get(segment, default)
    return Exchange(exch_str)
