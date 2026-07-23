"""Index-registry fallback in InMemoryInstrumentResolver + broker wires.

When the instrument master isn't loaded, ``resolve_ref`` must consult a
broker-specific ``index_fallback`` callable before raising KeyError, so bare
index ids (NSE:NIFTY, ...) still resolve to broker wire ids.
"""

from __future__ import annotations

import pytest

from domain.value_objects import InstrumentId
from plugins.brokers.common.instruments import InMemoryInstrumentResolver
from plugins.brokers.dhan.wire import DhanWire


def _fallback(iid: InstrumentId) -> dict | None:
    if str(iid).startswith("NSE:NIFTY"):
        return {"security_id": "13"}
    return None


def test_resolver_uses_index_fallback_on_miss() -> None:
    resolver = InMemoryInstrumentResolver(index_fallback=_fallback)
    ref = resolver.resolve_ref(InstrumentId.parse("NSE:NIFTY"))
    assert ref.require("security_id") == "13"


def test_resolver_fallback_miss_still_raises_keyerror() -> None:
    resolver = InMemoryInstrumentResolver(index_fallback=_fallback)
    with pytest.raises(KeyError):
        resolver.resolve_ref(InstrumentId.parse("NSE:GHOST"))


def test_resolver_without_fallback_raises_keyerror() -> None:
    resolver = InMemoryInstrumentResolver()
    with pytest.raises(KeyError):
        resolver.resolve_ref(InstrumentId.parse("NSE:NIFTY"))


def test_dhan_wire_security_id_falls_back_to_index_registry() -> None:
    w = DhanWire()
    assert w.security_id(InstrumentId.parse("NSE:NIFTY")) == "13"
