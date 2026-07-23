"""InMemoryInstrumentResolver — canonical-vs-wire-ref split, shared by dhan/upstox wire."""

from __future__ import annotations

import pytest

from domain.value_objects import InstrumentId
from plugins.brokers.common.instruments import BrokerWireRef, InMemoryInstrumentResolver


def test_register_then_resolve_ref_roundtrips() -> None:
    resolver = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:RELIANCE")
    resolver.register(iid, {"security_id": "1333"})

    ref = resolver.resolve_ref(iid)
    assert isinstance(ref, BrokerWireRef)
    assert ref.require("security_id") == "1333"


def test_resolve_ref_missing_raises_keyerror() -> None:
    resolver = InMemoryInstrumentResolver()
    with pytest.raises(KeyError):
        resolver.resolve_ref(InstrumentId.parse("NSE:UNKNOWN"))


def test_require_missing_wire_key_raises() -> None:
    resolver = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:RELIANCE")
    resolver.register(iid, {"security_id": "1333"})
    with pytest.raises(KeyError):
        resolver.resolve_ref(iid).require("instrument_key")


def test_reverse_finds_canonical_from_wire_value() -> None:
    resolver = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:RELIANCE")
    resolver.register(iid, {"security_id": "1333"})

    assert resolver.reverse("security_id", "1333") == iid
    assert resolver.reverse("security_id", "no-such-id") is None


def test_resolve_never_carries_wire_fields() -> None:
    resolver = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:RELIANCE")
    resolver.register(iid, {"security_id": "1333"})

    resolved = resolver.resolve(iid)
    assert resolved.exchange == "NSE"
    assert resolved.symbol == "RELIANCE"
    assert not hasattr(resolved, "wire")


def test_load_from_rows_bulk_populates_and_reports_stats() -> None:
    resolver = InMemoryInstrumentResolver()
    rows = [
        {"instrument_id": "NSE:RELIANCE", "wire": {"security_id": "1333"}},
        {"instrument_id": "NSE:TCS", "wire": {"security_id": "11536"}},
    ]

    stats = resolver.load_from_rows(rows, source="scrip_master")

    assert stats.total == 2
    assert stats.source == "scrip_master"
    assert resolver.is_loaded() is True
    assert resolver.resolve_ref(InstrumentId.parse("NSE:TCS")).require("security_id") == "11536"


def test_is_loaded_false_until_something_registered() -> None:
    resolver = InMemoryInstrumentResolver()
    assert resolver.is_loaded() is False
    resolver.register(InstrumentId.parse("NSE:RELIANCE"), {"security_id": "1333"})
    assert resolver.is_loaded() is True


def test_reregister_updates_reverse_index_and_drops_stale_entry() -> None:
    """Re-registering an instrument under a new wire id must not leave the old
    reverse-lookup entry pointing at it (O(1) reverse index must stay in sync)."""
    resolver = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:RELIANCE")
    resolver.register(iid, {"security_id": "1333"})
    assert resolver.reverse("security_id", "1333") == iid

    resolver.register(iid, {"security_id": "9999"})
    assert resolver.reverse("security_id", "9999") == iid
    assert resolver.reverse("security_id", "1333") is None
