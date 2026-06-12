from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.core.enums import (
    ExchangeSegment,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.models import OrderRequest
from brokers.dhan import DhanBroker
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.tests.fixtures.conftest import FIXTURE_CSV
from brokers.gateway import Gateway

pytestmark = pytest.mark.contract


def test_identical_security_id_and_segment(tmp_path) -> None:
    # 1. Initialize InstrumentService and load the minimal CSV snapshot
    service = InstrumentService(cache_dir=tmp_path / "instr_cache")
    service.load_snapshot(FIXTURE_CSV)

    # 2. Instantiate DhanBroker
    broker = DhanBroker(
        client_id="E2E-CLIENT",
        access_token="E2E-TOKEN",
        instrument_service=service,
    )

    # Mock connection states so we are mock-connected
    broker.is_connected = lambda: True
    broker._status = MagicMock()

    # Mock all the underlying client adapters that interact with the external Dhan APIs
    mock_market_data_client = MagicMock()
    mock_options_client = MagicMock()
    mock_order_client = MagicMock()
    mock_order_stream_client = MagicMock()

    # Inject mock clients into their respective adapters/handlers
    broker.market_data._market_data_client = mock_market_data_client
    broker.market_data._options_client = mock_options_client
    broker.order_client = mock_order_client
    broker.order_command._order_client = mock_order_client
    broker.order_stream._websocket_client = mock_order_stream_client
    mock_order_stream_client.is_connected.return_value = True

    # Verify connection status on order stream client is mocked to True
    broker.order_stream.connect()

    # Test cases to verify: (Symbol, Exchange, Expected Security ID, Expected Segment)
    # Using symbols present in api-scrip-master-minimal.csv
    test_cases = [
        ("RELIANCE", "NSE", "2885", ExchangeSegment.NSE),
        ("INFY", "NSE", "1594", ExchangeSegment.NSE),
        ("HDFCBANK", "NSE", "1333", ExchangeSegment.NSE),
        ("TCS", "NSE", "11536", ExchangeSegment.NSE),
    ]

    for symbol, exchange, expected_sid, expected_segment in test_cases:
        # Step A: Resolve Symbol using the canonical resolver
        result = broker.instrument_service.resolve_symbol(symbol, exchange)
        assert result.is_single, f"Expected single resolution for {symbol}"
        defn = result.definition
        assert defn.security_id == expected_sid
        assert defn.exchange_segment == expected_segment

        # Step B: Verify identical security ID and segment in Historical Request
        mock_market_data_client.get_historical_data.reset_mock()
        mock_market_data_client.get_historical_data.return_value = []

        broker.get_historical_data(
            symbol_or_sec_id=symbol,
            exchange_or_segment=exchange,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 5),
            timeframe_or_interval="1d",
        )

        mock_market_data_client.get_historical_data.assert_called_once()
        args, kwargs = mock_market_data_client.get_historical_data.call_args
        assert args[0] == expected_sid
        assert args[1] == expected_segment

        # Step C: Verify identical security ID in Live Subscription
        mock_order_stream_client.subscribe.reset_mock()
        mock_order_stream_client.subscribe.return_value = True

        broker.subscribe_order_stream([expected_sid])
        mock_order_stream_client.subscribe.assert_called_once_with([expected_sid])

        # Step D: Verify identical security ID and segment in Order Placement payload
        mock_order_client.place_order_payload.reset_mock()
        mock_order_client.place_order_payload.return_value = {
            "orderId": "123456",
            "status": "success",
        }

        order_request = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            exchange_segment=expected_segment,
            transaction_type=TransactionType.BUY,
            quantity=1,
            price=Decimal("100"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
            validity=Validity.DAY,
        )

        broker.order_command.place_order(order_request)

        mock_order_client.place_order_payload.assert_called_once()
        payload = mock_order_client.place_order_payload.call_args[0][0]
        assert payload["securityId"] == expected_sid
        assert payload["exchangeSegment"] == expected_segment.value

        # Step E: Verify Gateway resolves and invokes broker with same values
        # Initialize Gateway using our mocked broker
        gw = Gateway(broker=broker, auto_connect=False)

        # Gateway Historical request mapping check
        mock_market_data_client.get_historical_data.reset_mock()
        gw.history(symbol, exchange=exchange, lookback_days=5, timeframe="1d")
        mock_market_data_client.get_historical_data.assert_called_once()
        args, kwargs = mock_market_data_client.get_historical_data.call_args
        assert args[0] == expected_sid
        assert args[1] == expected_segment

        # Gateway Live Subscription mapping check
        mock_order_stream_client.subscribe.reset_mock()
        gw.stream(symbol, mode="ltp")
        mock_order_stream_client.subscribe.assert_called_once_with([expected_sid])
