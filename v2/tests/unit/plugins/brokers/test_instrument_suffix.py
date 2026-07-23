"""Exchange-suffix stripping (spec §3.1) — RELIANCE-EQ and RELIANCE both resolve."""

from __future__ import annotations

from domain.value_objects import InstrumentId
from plugins.brokers.common.instruments import InMemoryInstrumentResolver


def test_suffix_stripped_at_register_and_resolve() -> None:
    resolver = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:RELIANCE-EQ")
    resolver.register(iid, {"security_id": "1333"}, symbol="RELIANCE-EQ", exchange="NSE")

    # Bare symbol resolves (suffix stripped at register time).
    ref = resolver.resolve_ref(InstrumentId.parse("NSE:RELIANCE"))
    assert ref.require("security_id") == "1333"

    # Suffixed symbol still resolves (suffix stripped at resolve time).
    ref_eq = resolver.resolve_ref(InstrumentId.parse("NSE:RELIANCE-EQ"))
    assert ref_eq.require("security_id") == "1333"
