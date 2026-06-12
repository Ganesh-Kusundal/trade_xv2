from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.contracts import BrokerContractSuite
from brokers.common.core.connection import ConnectionStatus
from brokers.common.core.enums import OrderStatus, OrderType, TransactionType
from brokers.dhan import DhanBroker

pytestmark = pytest.mark.contract


class TestDhanBrokerContract(BrokerContractSuite):
    broker_name = "dhan"

    @pytest.fixture
    def broker(self, monkeypatch) -> DhanBroker:
        broker = DhanBroker(client_id="contract-client", access_token="contract-token")

        # 1. Mock connection state and instrument service resolution
        monkeypatch.setattr(broker, "_status", ConnectionStatus.CONNECTED)
        monkeypatch.setattr(broker, "is_connected", lambda: True)

        from brokers.common.core.enums import ExchangeSegment as CoreExchangeSegment
        from brokers.dhan.mapper.instruments import DhanInstrumentDefinition, ResolutionResult

        mock_defn = DhanInstrumentDefinition(
            symbol="RELIANCE",
            canonical_symbol="RELIANCE",
            exchange_segment=CoreExchangeSegment.NSE,
            security_id="2885",
            instrument_type="EQUITY",
        )
        mock_result = ResolutionResult(status="single", definition=mock_defn)
        monkeypatch.setattr(
            broker.instrument_service, "resolve_security_id", lambda symbol, exchange: "2885"
        )
        monkeypatch.setattr(
            broker.instrument_service, "resolve_symbol", lambda symbol, exchange: mock_result
        )

        # 2. Mock get_historical_intraday
        from brokers.common.core.models import HistoricalCandle

        mock_candles = [
            HistoricalCandle(
                timestamp=datetime.now(),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=120000,
            )
        ]
        monkeypatch.setattr(
            broker.market_data, "get_historical_intraday", lambda *args, **kwargs: mock_candles
        )

        # 3. Mock get_quote
        from brokers.common.core.models import Quote

        mock_quote = Quote(
            symbol="RELIANCE",
            exchange="NSE",
            last_price=Decimal("2500"),
            volume=100000,
            bid=Decimal("2499"),
            ask=Decimal("2501"),
        )
        monkeypatch.setattr(broker.market_data, "get_quote", lambda *args, **kwargs: mock_quote)

        # 4. Mock get_option_chain
        from brokers.common.core.models import OptionContract

        mock_contracts = [
            OptionContract(
                strike=Decimal("25000"),
                expiry="2026-07-30",
                ce_ltp=Decimal("150"),
                ce_volume=1000,
                ce_oi=500,
                pe_ltp=Decimal("140"),
                pe_volume=900,
                pe_oi=450,
            )
        ]
        monkeypatch.setattr(
            broker.options, "get_option_chain", lambda *args, **kwargs: mock_contracts
        )

        # 5. Mock get_depth
        from brokers.common.core.models import MarketDepth, MarketDepthLevel

        mock_depth = MarketDepth(
            symbol="RELIANCE",
            bids=[MarketDepthLevel(price=Decimal("2500"), quantity=100)],
            asks=[MarketDepthLevel(price=Decimal("2501"), quantity=100)],
        )
        monkeypatch.setattr(broker.market_data, "get_depth", lambda *args, **kwargs: mock_depth)

        # 6. Mock place_order
        from brokers.common.core.models import OrderResponse

        mock_order_res = OrderResponse(
            success=True, order_id="DHAN12345", message="Success", order_status=OrderStatus.PENDING
        )
        monkeypatch.setattr(
            broker.order_command, "place_order", lambda *args, **kwargs: mock_order_res
        )

        # 7. Mock get_order_by_id and get_order_list
        mock_raw_order = {
            "orderId": "DHAN12345",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "quantity": 10,
            "filledQty": 0,
            "price": 2500.0,
            "triggerPrice": 0.0,
            "orderStatus": "PENDING",
            "productType": "INTRADAY",
            "validity": "DAY",
            "averagePrice": 0.0,
            "rejectReason": "",
            "correlationId": "corr-123",
        }
        monkeypatch.setattr(broker, "get_order_by_id", lambda *args: mock_raw_order)

        from brokers.common.core.models import Order

        mock_pydantic_orders = [
            Order(
                order_id="DHAN12345",
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type=TransactionType.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                price=Decimal("2500"),
                status=OrderStatus.PENDING,
            )
        ]
        monkeypatch.setattr(broker, "get_order_list", lambda *args: mock_pydantic_orders)

        # 8. Mock get_positions / get_holdings / get_fund_limits / get_trades
        mock_positions_res = {
            "status": "success",
            "data": [
                {
                    "securityId": "2885",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "netQuantity": 100,
                    "buyAveragePrice": 2480.0,
                    "lastPrice": 2500.0,
                    "unrealizedPnl": 2000.0,
                    "realizedPnl": 0.0,
                    "productType": "INTRADAY",
                }
            ],
        }
        mock_holdings_res = {
            "status": "success",
            "data": [
                {
                    "securityId": "2885",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "quantity": 50,
                    "availableQuantity": 50,
                    "costPrice": 2450.0,
                    "lastPrice": 2500.0,
                    "pnlValue": 2500.0,
                }
            ],
        }
        mock_funds_res = {
            "status": "success",
            "data": {"availableBalance": 500000.0, "usedMargin": 5000.0, "totalMargin": 505000.0},
        }
        mock_trades_res = {
            "status": "success",
            "data": [
                {
                    "tradeId": "T123",
                    "orderId": "DHAN12345",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "tradedQty": 10,
                    "tradedPrice": 2500.0,
                    "productType": "INTRADAY",
                }
            ],
        }

        def mock_execute(executor, fn):
            return fn()

        monkeypatch.setattr(broker, "_execute_with_auth", mock_execute)

        mock_dhan = MagicMock()
        mock_dhan.get_positions.return_value = mock_positions_res
        mock_dhan.get_holdings.return_value = mock_holdings_res
        mock_dhan.get_fund_limits.return_value = mock_funds_res
        mock_dhan.get_trade_book.return_value = mock_trades_res
        broker._dhan = mock_dhan

        return broker
