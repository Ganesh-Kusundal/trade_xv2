"""Phase 4 structural smoke checks — authenticate parity, Money eq, trade helper, no asyncio.run."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from domain.entities.trade import build_domain_trade
from domain.primitives.value_objects import Money
from domain.types import Side


def test_money_eq_is_money_only():
    assert Money(10, "INR") == Money(Decimal("10"), "INR")
    assert Money(10, "INR") != Money(10, "USD")
    assert Money(10, "INR") != 10
    assert Money.coerce(10, "INR") == Money(10, "INR")


def test_build_domain_trade_shared():
    t = build_domain_trade(
        trade_id="t1",
        symbol="RELIANCE",
        side="BUY",
        quantity=2,
        price="100.5",
        trade_value="201",
    )
    assert t.symbol == "RELIANCE"
    assert t.side == Side.BUY
    assert int(t.quantity) == 2
    assert t.price == Money("100.5")


def test_dhan_authenticate_ensures_token_not_ws_liveness():
    from brokers.providers.dhan.wire import DhanWireAdapter

    client = SimpleNamespace(access_token="tok", _try_refresh_token=lambda: False)
    conn = SimpleNamespace(_client=client, _auth=None, _session_manager=None, market_feed=None)
    wire = DhanWireAdapter.__new__(DhanWireAdapter)
    wire._conn = conn
    assert wire.authenticate() is True
    client.access_token = ""
    assert wire.authenticate() is False


def test_build_infrastructure_is_sync_no_asyncio_run():
    import inspect

    from runtime.broker_infrastructure import build_infrastructure

    assert not inspect.iscoroutinefunction(build_infrastructure)
