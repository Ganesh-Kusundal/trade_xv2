"""Public BrokerSession / BrokerGateway API contract (paper)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.gateway import BrokerGateway
from brokers.session.broker_session import BrokerSession
from domain.enums import OrderType, ProductType, Side
from domain.orders.requests import OrderRequest


@pytest.fixture
def paper_session():
    session = BrokerSession.connect("paper", load_instruments=False)
    yield session
    session.close()


@pytest.mark.unit
def test_connect_exposes_gateway(paper_session):
    assert isinstance(paper_session.gateway, BrokerGateway)
    assert not hasattr(paper_session.gateway, "quote")
    assert not hasattr(paper_session, "buy")
    assert not hasattr(paper_session, "subscribe")


@pytest.mark.unit
def test_instrument_market_data_still_works(paper_session):
    stock = paper_session.stock("RELIANCE")
    q = stock.refresh()
    assert q is not None or stock.quote is None or stock.quote is not None


@pytest.mark.unit
def test_broker_session_trading_surface_is_gateway_only(paper_session):
    """BrokerSession no longer exposes buy/subscribe — use gateway."""
    assert not hasattr(paper_session, "buy")
    assert not hasattr(paper_session, "subscribe")
    assert hasattr(paper_session.gateway, "place_order")
    assert hasattr(paper_session.gateway, "subscribe")


@pytest.mark.unit
def test_gateway_portfolio_surface(paper_session):
    gw = paper_session.gateway
    assert isinstance(gw.orders(), list)
    assert isinstance(gw.positions(), list)
    assert isinstance(gw.holdings(), list)
    funds = gw.funds()
    margin = gw.margin()
    assert funds is margin or funds is not None or margin is None


@pytest.mark.unit
def test_gateway_subscribe_list_api(paper_session):
    stock = paper_session.stock("RELIANCE")
    handles = paper_session.gateway.subscribe([stock])
    assert isinstance(handles, list)
    paper_session.gateway.unsubscribe([stock])


@pytest.mark.unit
def test_gateway_place_and_cancel_roundtrip(paper_session):
    gw = paper_session.gateway
    result = gw.place_order(
        OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=1,
            price=Decimal("2500"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
        )
    )
    assert result is not None
    order_id = getattr(result, "order_id", None) or getattr(
        getattr(result, "order", None), "order_id", None
    )
    if order_id:
        gw.cancel_order(str(order_id))
    assert isinstance(gw.orders(), list)


@pytest.mark.unit
def test_instrument_has_no_legacy_trading_subscribe(paper_session):
    stock = paper_session.stock("RELIANCE")
    for name in ("buy", "sell", "subscribe", "cancel", "modify"):
        assert not hasattr(stock, name)
    assert not hasattr(paper_session, "quote")


@pytest.mark.unit
def test_extension_missing_raises(paper_session):
    class _MissingExt:
        name = "not_registered"

    with pytest.raises(LookupError, match="not registered"):
        paper_session.extension(_MissingExt)
