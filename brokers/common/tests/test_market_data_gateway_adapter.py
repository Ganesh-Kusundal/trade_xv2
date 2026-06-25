"""Integration tests for MarketDataGatewayAdapter using PaperGateway."""

import pytest

from brokers.common.adapters.market_data_gateway_adapter import wrap_market_gateway
from brokers.common.broker_port import HistoricalBarRequest, QuotaToken
from brokers.common.capabilities import BrokerCapabilities
from brokers.paper import PaperGateway
from domain.enums import OrderType, ProductType, Side, Validity
from domain.historical import InstrumentRef
from domain.requests import OrderRequest


@pytest.fixture
def paper_adapter():
    caps = BrokerCapabilities(
        broker_id="paper",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_historical_data=True,
        supports_live_market_data=True,
    )
    return wrap_market_gateway(PaperGateway(), "paper", capabilities=caps)


class TestMarketDataGatewayAdapter:
    @pytest.mark.asyncio
    async def test_list_capabilities(self, paper_adapter):
        desc = paper_adapter.list_capabilities()
        assert desc.broker_id == "paper"
        assert desc.capabilities.supports_place_order

    @pytest.mark.asyncio
    async def test_get_quote_snapshot(self, paper_adapter):
        token = QuotaToken("paper", "quotes", "PORTFOLIO_READ", "t1")
        quote = await paper_adapter.get_quote_snapshot(
            InstrumentRef("RELIANCE", "NSE"), quota=token
        )
        assert quote.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_place_order_via_adapter(self, paper_adapter):
        token = QuotaToken("paper", "orders", "EXECUTION_CRITICAL", "t2")
        request = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            product_type=ProductType.INTRADAY,
            validity=Validity.DAY,
        )
        response = await paper_adapter.place_order(request, quota=token)
        assert response.success

    @pytest.mark.asyncio
    async def test_get_historical_bars(self, paper_adapter):
        token = QuotaToken("paper", "historical", "HISTORICAL_BACKFILL", "t3")
        request = HistoricalBarRequest(
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
            from_date="2025-01-01",
            to_date="2025-01-10",
            request_id="paper-hist-1",
        )
        bars = await paper_adapter.get_historical_bars(request, quota=token)
        assert isinstance(bars, list)

    @pytest.mark.asyncio
    async def test_health(self, paper_adapter):
        health = await paper_adapter.health()
        assert health.broker_id == "paper"
        assert health.alive
