"""InstrumentResolver + ConnectError."""

from __future__ import annotations

from domain.connect_errors import OMS_REQUIRED, ConnectError
from domain.instruments.resolver import InstrumentResolver


def test_resolver_fuzzy():
    r = InstrumentResolver(known_symbols=["RELIANCE", "TCS", "INFY"])
    iid = r.resolve("RELINCE")  # typo
    assert iid.underlying == "RELIANCE"
    d = r.doctor("RELINCE")
    assert d["ok"] is True
    assert d["canonical"] == "NSE:RELIANCE"


def test_connect_error_to_dict():
    err = ConnectError(
        "need oms",
        code=OMS_REQUIRED,
        broker_id="dhan",
        mode="trade",
        remediation="start API",
        trace_id="abc",
    )
    d = err.to_dict()
    assert d["code"] == OMS_REQUIRED
    assert "start API" in str(err)
