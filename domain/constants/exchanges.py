"""Canonical exchange identifiers and segment aliases (REF-2)."""

from __future__ import annotations

from domain.types import ExchangeSegment

# Human-friendly exchange codes used in APIs, CLI, and tests.
NSE = "NSE"
BSE = "BSE"
NFO = "NFO"
BFO = "BFO"
MCX = "MCX"
CDS = "CDS"
BCD = "BCD"
IDX = "IDX"

# Wire-format segment strings (broker payloads).
WIRE_NSE_EQ = "NSE_EQ"
WIRE_BSE_EQ = "BSE_EQ"
WIRE_NSE_FNO = "NSE_FNO"
WIRE_BSE_FNO = "BSE_FNO"
WIRE_MCX_COMM = "MCXCOMM"
WIRE_NSE_CURRENCY = "NSE_CURRENCY"
WIRE_BSE_CURRENCY = "BSE_CURRENCY"
WIRE_IDX = "IDX_I"

# Short code → canonical ExchangeSegment (delegates to exchange_segments module).
SHORT_TO_SEGMENT: dict[str, ExchangeSegment] = {
    NSE: ExchangeSegment.NSE,
    WIRE_NSE_EQ: ExchangeSegment.NSE,
    BSE: ExchangeSegment.BSE,
    WIRE_BSE_EQ: ExchangeSegment.BSE,
    NFO: ExchangeSegment.NSE_FNO,
    WIRE_NSE_FNO: ExchangeSegment.NSE_FNO,
    BFO: ExchangeSegment.BSE_FNO,
    WIRE_BSE_FNO: ExchangeSegment.BSE_FNO,
    MCX: ExchangeSegment.MCX,
    WIRE_MCX_COMM: ExchangeSegment.MCX,
    CDS: ExchangeSegment.NSE_CURRENCY,
    WIRE_NSE_CURRENCY: ExchangeSegment.NSE_CURRENCY,
    BCD: ExchangeSegment.BSE_CURRENCY,
    WIRE_BSE_CURRENCY: ExchangeSegment.BSE_CURRENCY,
    IDX: ExchangeSegment.IDX_I,
    WIRE_IDX: ExchangeSegment.IDX_I,
}

__all__ = [
    "BCD",
    "BFO",
    "BSE",
    "CDS",
    "IDX",
    "MCX",
    "NFO",
    "NSE",
    "SHORT_TO_SEGMENT",
    "WIRE_BSE_CURRENCY",
    "WIRE_BSE_EQ",
    "WIRE_BSE_FNO",
    "WIRE_IDX",
    "WIRE_MCX_COMM",
    "WIRE_NSE_CURRENCY",
    "WIRE_NSE_EQ",
    "WIRE_NSE_FNO",
]
