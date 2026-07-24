"""Atomic instrument-master reload + duplicate detection.

Covers the resolver-level bulk swap (InMemoryInstrumentResolver.load_from_rows)
and the per-broker loader rewiring that routes through it instead of
per-row register() calls.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from domain.value_objects import InstrumentId
from plugins.brokers.common.instruments import InMemoryInstrumentResolver
from plugins.brokers.dhan.adapters.instruments import DhanInstrumentAdapter
from plugins.brokers.upstox.adapters.instruments import UpstoxInstrumentAdapter


# ---------------------------------------------------------------------------
# Resolver-level: atomic swap + duplicate detection
# ---------------------------------------------------------------------------


def test_load_from_rows_swaps_atomically() -> None:
    resolver = InMemoryInstrumentResolver()
    resolver.register(InstrumentId.equity("NSE", "OLD"), {"security_id": "1"})
    wire_before = resolver._wire

    rows = [{"instrument_id": InstrumentId.equity("NSE", "NEW"), "wire": {"security_id": "2"}}]
    resolver.load_from_rows(rows, source="test")

    # The dict object itself was replaced in one step, not mutated in place.
    assert resolver._wire is not wire_before
    assert resolver.reverse("security_id", "2") == InstrumentId.equity("NSE", "NEW")
    # Old data is gone — load_from_rows replaces, it doesn't merge.
    assert resolver.reverse("security_id", "1") is None


def test_load_from_rows_logs_duplicates(caplog) -> None:
    resolver = InMemoryInstrumentResolver()
    rows = [
        {"instrument_id": InstrumentId.equity("NSE", "DUP"), "wire": {"security_id": "1"}},
        {"instrument_id": InstrumentId.equity("NSE", "DUP"), "wire": {"security_id": "2"}},
    ]
    with caplog.at_level(logging.WARNING):
        stats = resolver.load_from_rows(rows, source="test")

    assert stats.total == 1  # last-write-wins
    assert resolver.reverse("security_id", "2") == InstrumentId.equity("NSE", "DUP")
    assert any("duplicate" in r.message.lower() for r in caplog.records)


def test_load_from_rows_no_warning_when_no_duplicates(caplog) -> None:
    resolver = InMemoryInstrumentResolver()
    rows = [
        {"instrument_id": InstrumentId.equity("NSE", "A"), "wire": {"security_id": "1"}},
        {"instrument_id": InstrumentId.equity("NSE", "B"), "wire": {"security_id": "2"}},
    ]
    with caplog.at_level(logging.WARNING):
        resolver.load_from_rows(rows, source="test")
    assert not any("duplicate" in r.message.lower() for r in caplog.records)


def test_register_still_works_incrementally_after_bulk_load() -> None:
    """register() (used by index/MCX-supplement registration) must keep
    working for incremental single-instrument adds alongside bulk loads."""
    resolver = InMemoryInstrumentResolver()
    resolver.load_from_rows(
        [{"instrument_id": InstrumentId.equity("NSE", "A"), "wire": {"security_id": "1"}}],
        source="bulk",
    )
    resolver.register(InstrumentId.equity("NSE", "B"), {"security_id": "2"})
    assert resolver.reverse("security_id", "1") == InstrumentId.equity("NSE", "A")
    assert resolver.reverse("security_id", "2") == InstrumentId.equity("NSE", "B")


# ---------------------------------------------------------------------------
# Loader-level: Dhan CSV parse routes through the atomic bulk path
# ---------------------------------------------------------------------------

DUPLICATE_CSV = """\
SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS,SEM_TICK_SIZE,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE
RELIANCE-EQ,2885,NSE,E,EQUITY,1,0.05,,,,
RELIANCE-EQ,9999,NSE,E,EQUITY,1,0.05,,,,
"""


def test_dhan_csv_parse_logs_duplicate_canonical_ids(caplog) -> None:
    adapter = DhanInstrumentAdapter(transport=MagicMock())
    with caplog.at_level(logging.WARNING):
        instruments = adapter._parse_csv_to_instruments(DUPLICATE_CSV)
    assert len(instruments) == 2  # both Instrument objects returned...
    assert len(adapter._by_id) == 1  # ...but the by-id map dedups (last-write-wins)
    assert any("duplicate" in r.message.lower() for r in caplog.records)


def test_dhan_csv_parse_registers_wire_via_bulk_path() -> None:
    """End-to-end: security_id lookup works after a parse that now routes
    through DhanWire.register_bulk() -> resolver.load_from_rows()."""
    adapter = DhanInstrumentAdapter(transport=MagicMock())
    adapter._parse_csv_to_instruments(
        "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_INSTRUMENT_NAME,"
        "SEM_LOT_UNITS,SEM_TICK_SIZE,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE\n"
        "RELIANCE-EQ,2885,NSE,E,EQUITY,1,0.05,,,,\n"
    )
    assert adapter._wire.security_id(InstrumentId.equity("NSE", "RELIANCE")) == "2885"


# ---------------------------------------------------------------------------
# Loader-level: Upstox JSON rows route through the atomic bulk path
# ---------------------------------------------------------------------------


def test_upstox_rows_logs_duplicate_canonical_ids(caplog) -> None:
    adapter = UpstoxInstrumentAdapter(transport=MagicMock())
    rows = [
        {"symbol": "RELIANCE", "segment": "NSE_EQ", "instrument_key": "NSE_EQ|A"},
        {"symbol": "RELIANCE", "segment": "NSE_EQ", "instrument_key": "NSE_EQ|B"},
    ]
    with caplog.at_level(logging.WARNING):
        instruments = adapter._rows_to_instruments(rows)
    assert len(instruments) == 2
    assert len(adapter._by_id) == 1
    assert any("duplicate" in r.message.lower() for r in caplog.records)


def test_upstox_rows_registers_wire_via_bulk_path() -> None:
    adapter = UpstoxInstrumentAdapter(transport=MagicMock())
    adapter._rows_to_instruments([{"symbol": "RELIANCE", "segment": "NSE_EQ", "instrument_key": "NSE_EQ|INE002A01018"}])
    assert adapter._wire.instrument_key(InstrumentId.equity("NSE", "RELIANCE")) == "NSE_EQ|INE002A01018"
