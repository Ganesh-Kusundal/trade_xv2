"""Domain market entity invariants — no broker tokens on public shapes."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from domain.candles.historical import InstrumentRef
from domain.entities.market import MarketDepth, MarketTick, Quote
from domain.entities.options import FutureChain, FutureContract, OptionChain
from domain.provenance import DataProvenance


@pytest.mark.unit
def test_quote_snapshot_has_no_token_keys() -> None:
    q = Quote(symbol="RELIANCE", ltp=Decimal("100"))
    snap = q.snapshot()
    assert "security_id" not in snap
    assert "instrument_token" not in snap


@pytest.mark.unit
def test_market_tick_domain_fields() -> None:
    tick = MarketTick(
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        ltp=Decimal("100.5"),
        event_time=datetime.now(timezone.utc),
        provenance=DataProvenance.now("dhan", "stream"),
        broker_id="dhan",
        session_id="sess-1",
    )
    assert tick.broker_id == "dhan"
    assert tick.ltp == Decimal("100.5")
    from dataclasses import fields

    names = {f.name for f in fields(tick)}
    assert "security_id" not in names


@pytest.mark.unit
def test_future_chain_to_dict_strips_tokens() -> None:
    chain = FutureChain(
        underlying="NIFTY",
        exchange="NFO",
        contracts=(FutureContract(symbol="NIFTY24JULFUT", expiry="2024-07-25", lot_size=25),),
    )
    payload = chain.to_dict()
    assert "security_id" not in str(payload)


@pytest.mark.unit
def test_market_depth_snapshot() -> None:
    depth = MarketDepth(symbol="RELIANCE")
    snap = depth.snapshot()
    assert snap["symbol"] == "RELIANCE"
    assert "security_id" not in snap


@pytest.mark.unit
def test_option_chain_to_dict() -> None:
    chain = OptionChain(underlying="NIFTY", exchange="NFO", expiry="2024-07-25")
    payload = chain.to_dict()
    assert "security_id" not in payload
