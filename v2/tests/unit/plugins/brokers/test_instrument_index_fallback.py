"""Index resolution at the core (no resolver fallback).

Indices (NIFTY, BANKNIFTY, SENSEX, ...) resolve directly from the shared
index registry inside each broker's wire lookup methods — ``security_id`` /
``instrument_key`` / ``get_segment`` — so they work even when the instrument
master isn't loaded, and the segment is correct (IDX_I / NSE_INDEX), not the
equity segment.
"""

from __future__ import annotations

import pytest

from domain.value_objects import InstrumentId
from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.upstox.wire import UpstoxWire


def test_dhan_wire_index_security_id_resolves_at_core() -> None:
    w = DhanWire()
    assert w.security_id(InstrumentId.parse("NSE:NIFTY")) == "13"
    assert w.security_id(InstrumentId.parse("NSE:BANKNIFTY")) == "25"


def test_dhan_wire_index_segment_is_correct_not_equity() -> None:
    w = DhanWire()
    # Core fix: the segment for an index must be IDX_I, not NSE_EQ.
    assert w.get_segment(InstrumentId.parse("NSE:NIFTY")) == "IDX_I"
    assert w.get_segment(InstrumentId.parse("NSE:RELIANCE")) == "NSE_EQ"


def test_upstox_wire_index_instrument_key_resolves_at_core() -> None:
    w = UpstoxWire()
    assert w.instrument_key(InstrumentId.parse("NSE:NIFTY")) == "NSE_INDEX|Nifty 50"


def test_upstox_wire_index_segment_is_correct_not_equity() -> None:
    w = UpstoxWire()
    assert w.get_segment(InstrumentId.parse("NSE:NIFTY")) == "NSE_INDEX"
    assert w.get_segment(InstrumentId.parse("NSE:RELIANCE")) == "NSE_EQ"


def test_non_index_without_master_still_raises() -> None:
    w = DhanWire()
    with pytest.raises(KeyError):
        w.security_id(InstrumentId.parse("NSE:GHOST"))


# ── Derivatives ON an index must never resolve as the index itself ─────────


def test_dhan_derivative_on_index_does_not_resolve_as_index() -> None:
    w = DhanWire()
    w.register_security(InstrumentId.parse("NFO:NIFTY:20260730:FUT"), "44321")
    # The future's own security_id — NOT "13" (NIFTY index).
    assert w.security_id(InstrumentId.parse("NFO:NIFTY:20260730:FUT")) == "44321"
    # F&O segment — NOT "IDX_I".
    assert w.get_segment(InstrumentId.parse("NFO:NIFTY:20260730:FUT")) == "NSE_FNO"


def test_dhan_option_on_index_does_not_resolve_as_index() -> None:
    w = DhanWire()
    iid = InstrumentId.parse("NFO:NIFTY:20260730:24000:CE")
    w.register_security(iid, "98765")
    assert w.security_id(iid) == "98765"  # NOT "13"
    assert w.get_segment(iid) == "NSE_FNO"


def test_upstox_derivative_on_index_does_not_resolve_as_index() -> None:
    w = UpstoxWire()
    iid = InstrumentId.parse("NFO:NIFTY:20260730:24000:CE")
    w.register_key(iid, "NSE_FO|12345")
    # The option's own key — NOT "NSE_INDEX|Nifty 50".
    assert w.instrument_key(iid) == "NSE_FO|12345"
    assert w.get_segment(iid) == "NSE_FO"  # NOT "NSE_INDEX"


def test_upstox_future_on_index_segment_not_index() -> None:
    w = UpstoxWire()
    assert w.get_segment(InstrumentId.parse("NFO:BANKNIFTY:20260730:FUT")) == "NSE_FO"


def test_dhan_history_instrument_type_distinguishes_fut_opt() -> None:
    w = DhanWire()
    assert w.get_instrument_type(InstrumentId.parse("NFO:NIFTY:20260730:FUT")) == "FUTIDX"
    assert w.get_instrument_type(InstrumentId.parse("NFO:NIFTY:20260730:24000:CE")) == "OPTIDX"
    assert w.get_instrument_type(InstrumentId.parse("NSE:RELIANCE")) == "EQUITY"
    assert w.get_instrument_type(InstrumentId.parse("MCX:CRUDEOIL:20260720:FUT")) == "FUTCOM"
