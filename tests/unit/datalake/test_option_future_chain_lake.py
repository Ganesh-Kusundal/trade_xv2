"""TOS-P6-002 — lake option/future chain reads (empty lake returns empty, not error)."""

from __future__ import annotations

from datalake.gateway import DataLakeGateway


def test_option_chain_empty_lake():
    gw = DataLakeGateway(root="market_data")
    chain = gw.option_chain("NIFTY")
    assert chain["underlying"] == "NIFTY"
    assert isinstance(chain["calls"], list)
    assert isinstance(chain["puts"], list)


def test_future_chain_empty_lake():
    gw = DataLakeGateway(root="market_data")
    assert gw.future_chain("NIFTY") == []
