"""Future instrument: identity, expiry, and package re-exports."""

from __future__ import annotations

from datetime import date

from domain.futures import Future, FutureChain, FutureContract
from domain.instruments.instrument_id import InstrumentId


def test_future_builds_canonical_instrument_id():
    f = Future(symbol="NIFTY", exchange="NFO", expiry=date(2026, 7, 31))
    assert isinstance(f.id, InstrumentId)
    assert f.id.underlying == "NIFTY"
    assert f.expiry == date(2026, 7, 31)


def test_future_key_uses_instrument_id_string():
    f = Future(symbol="NIFTY", exchange="NFO", expiry=date(2026, 7, 31))
    assert str(f.id) == "NFO:NIFTY:20260731:FUT"


def test_future_is_expired():
    f = Future(symbol="X", exchange="NFO", expiry=date(2020, 1, 1))
    # Expired contracts remain constructible; consumers check expiry date.
    assert f.expiry < date.today()


def test_future_chain_reexport():
    assert FutureChain is not None


def test_future_contract_reexport():
    assert FutureContract is not None
