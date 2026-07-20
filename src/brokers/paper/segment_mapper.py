"""Paper broker segment mapper — domain-only wire mapping (no live broker deps)."""

from __future__ import annotations

from domain.constants.exchanges import (
    WIRE_BSE_EQ,
    WIRE_BSE_FNO,
    WIRE_IDX,
    WIRE_NSE_CURRENCY,
    WIRE_NSE_EQ,
    WIRE_NSE_FNO,
)
from domain.constants.market import DEFAULT_EXCHANGE_SEGMENT_FALLBACK
from domain.exchange_segments import parse_segment
from domain.types import ExchangeSegment

_DEFAULT_WIRE = DEFAULT_EXCHANGE_SEGMENT_FALLBACK or WIRE_NSE_EQ

_SEGMENT_TO_WIRE: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: WIRE_NSE_EQ,
    ExchangeSegment.BSE: WIRE_BSE_EQ,
    ExchangeSegment.NSE_FNO: WIRE_NSE_FNO,
    ExchangeSegment.BSE_FNO: WIRE_BSE_FNO,
    ExchangeSegment.MCX: "MCX_COMM",
    ExchangeSegment.NSE_CURRENCY: WIRE_NSE_CURRENCY,
    ExchangeSegment.IDX_I: WIRE_IDX,
}

_EXCHANGE_TO_WIRE: dict[str, str] = {
    "NSE": WIRE_NSE_EQ,
    "BSE": WIRE_BSE_EQ,
    "MCX": "MCX_COMM",
    "NFO": WIRE_NSE_FNO,
    "CDS": WIRE_NSE_CURRENCY,
    "INDEX": WIRE_IDX,
}


class PaperSegmentMapper:
    """SegmentMapper for simulated trading (NSE-centric defaults)."""

    broker_id = "paper"

    def to_wire(self, segment: ExchangeSegment) -> str:
        return _SEGMENT_TO_WIRE.get(segment, _DEFAULT_WIRE)

    def from_wire(self, wire: str) -> ExchangeSegment:
        parsed = parse_segment(wire)
        return parsed or ExchangeSegment.NSE

    def from_exchange(self, exchange: str) -> ExchangeSegment:
        wire = _EXCHANGE_TO_WIRE.get(str(exchange or "NSE").upper(), _DEFAULT_WIRE)
        return self.from_wire(wire)
