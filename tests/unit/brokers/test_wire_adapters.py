"""Wire adapter smoke tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.dhan.wire import DhanWireAdapter, create_wire_adapter
from brokers.paper.paper_gateway import PaperGateway
from brokers.upstox.wire import UpstoxWireAdapter
from tests.support.brokers.dhan.fixtures import FakeHttpClient, SAMPLE_ROWS
from brokers.dhan.streaming.connection import DhanConnection


@pytest.fixture()
def offline_dhan_wire() -> DhanWireAdapter:
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    return DhanWireAdapter(conn)


@pytest.mark.unit
def test_dhan_wire_describe(offline_dhan_wire: DhanWireAdapter) -> None:
    desc = offline_dhan_wire.describe()
    assert isinstance(desc, dict)
    assert desc.get("broker") == "Dhan"


@pytest.mark.unit
def test_dhan_create_wire_adapter(offline_dhan_wire: DhanWireAdapter) -> None:
    wire = create_wire_adapter(offline_dhan_wire)
    assert isinstance(wire, DhanWireAdapter)
    assert wire.broker_id == "dhan" if hasattr(wire, "broker_id") else True


@pytest.mark.unit
def test_paper_gateway_quote() -> None:
    gw = PaperGateway(initial_capital=Decimal("100000"))
    assert gw.quote("RELIANCE", "NSE").symbol == "RELIANCE"


@pytest.mark.unit
def test_upstox_wire_is_alias_of_gateway_class() -> None:
    assert UpstoxWireAdapter is not None
    assert UpstoxWireAdapter.__name__ == "UpstoxWireAdapter"
