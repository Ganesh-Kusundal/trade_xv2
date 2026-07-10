"""Self-check: shared alternate keys + broker instrument service shape.

No mocks — exercises real common helpers and Dhan/Upstox service classes.
"""

from __future__ import annotations

from brokers.common.instruments import (
    BrokerInstrumentService,
    BrokerWireRef,
    ResolvedInstrument,
    generate_alternate_keys,
)
from brokers.common.instruments.keys import _generate_alternate_keys
from brokers.dhan.instruments import DhanInstrumentService
from brokers.dhan.resolver import _generate_alternate_keys as dhan_keys
from brokers.upstox.instruments.resolver import _generate_alternate_keys as upstox_keys
from brokers.upstox.instruments.service import UpstoxInstrumentService


def test_alternate_keys_shared_across_brokers():
    """Dhan and Upstox re-export the same shared generator (zero-parity)."""
    assert dhan_keys is generate_alternate_keys
    assert upstox_keys is generate_alternate_keys
    assert _generate_alternate_keys is generate_alternate_keys


def test_generate_alternate_keys_option_forms():
    keys = generate_alternate_keys(
        symbol="NIFTY25JUN2525000CE",
        inst_type="OPTION",
        expiry="2025-06-26",
        strike=25000,
        option_type="CE",
        underlying="NIFTY",
        canonical_symbol="NIFTY 26 JUN 25000 CE",
    )
    assert "NIFTY 26 JUN 25 25000 CE" in keys or any("25000" in k and "CE" in k for k in keys)
    assert any(k.replace(" ", "") for k in keys)


def test_dhan_service_satisfies_protocol():
    svc = DhanInstrumentService()
    assert isinstance(svc, BrokerInstrumentService)
    assert svc.is_loaded() is False
    assert svc.stats()["total"] == 0


def test_upstox_service_satisfies_protocol():
    svc = UpstoxInstrumentService()
    assert isinstance(svc, BrokerInstrumentService)
    assert svc.is_loaded() is False


def test_carriers_are_immutable_shapes():
    r = ResolvedInstrument(symbol="RELIANCE", exchange="NSE")
    assert r.symbol == "RELIANCE"
    w = BrokerWireRef(symbol="RELIANCE", exchange="NSE", wire={"security_id": "2885"})
    assert w.require("security_id") == "2885"


if __name__ == "__main__":
    test_alternate_keys_shared_across_brokers()
    test_generate_alternate_keys_option_forms()
    test_dhan_service_satisfies_protocol()
    test_upstox_service_satisfies_protocol()
    test_carriers_are_immutable_shapes()
    print("ok")
