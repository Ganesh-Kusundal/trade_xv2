"""Tests for FieldMapping protocol and implementations.

Verifies that:
1. DhanFieldMapping correctly maps Dhan API responses
2. UpstoxFieldMapping correctly maps Upstox API responses
3. Order.from_broker_dict works with both mappings
4. Backward compatibility is maintained (default mapping is Dhan)
"""

import pytest
from decimal import Decimal

from brokers.common.core.models import Order
from brokers.common.core.types import OrderStatus, OrderType, Side
from brokers.dhan.order_mapping import DhanFieldMapping
from brokers.upstox.order_mapping import UpstoxFieldMapping


class TestDhanFieldMapping:
    """Test Dhan-specific field name mapping."""

    def test_map_complete_dhan_order(self):
        """Map a complete Dhan order response."""
        raw = {
            "orderId": "12345",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "orderStatus": "COMPLETE",
            "quantity": 10,
            "filledQty": 10,
            "price": "2500.00",
            "averagePrice": "2498.50",
            "rejectReason": "",
        }
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert order.order_id == "12345"
        assert order.symbol == "RELIANCE"
        assert order.exchange == "NSE_EQ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.FILLED
        assert order.quantity == 10
        assert order.filled_quantity == 10
        assert order.price == Decimal("2500.00")
        assert order.avg_price == Decimal("2498.50")

    def test_map_sell_order(self):
        """Map a SELL order."""
        raw = {
            "orderId": "67890",
            "tradingSymbol": "TCS",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "SELL",
            "orderType": "MARKET",
            "orderStatus": "OPEN",
            "quantity": 5,
            "filledQty": 0,
        }
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert order.side == Side.SELL
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.OPEN

    def test_map_stoploss_limit_alias(self):
        """Map STOPLOSS_LIMIT to STOP_LOSS."""
        raw = {"orderType": "STOPLOSS_LIMIT"}
        mapping = DhanFieldMapping()
        ot = mapping.map_order_type(raw)
        assert ot == "STOP_LOSS"

    def test_map_stoploss_market_alias(self):
        """Map STOPLOSS_MARKET to STOP_LOSS_MARKET."""
        raw = {"orderType": "STOPLOSS_MARKET"}
        mapping = DhanFieldMapping()
        ot = mapping.map_order_type(raw)
        assert ot == "STOP_LOSS_MARKET"

    def test_map_stoploss_market_hyphen_alias(self):
        """Map STOPLOSS-MARKET to STOP_LOSS_MARKET."""
        raw = {"orderType": "STOPLOSS-MARKET"}
        mapping = DhanFieldMapping()
        ot = mapping.map_order_type(raw)
        assert ot == "STOP_LOSS_MARKET"

    def test_map_empty_fields(self):
        """Map empty dict to default values."""
        raw = {}
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert order.order_id == ""
        assert order.symbol == ""
        assert order.exchange == "NSE"
        assert order.side == Side.BUY  # Default
        assert order.order_type == OrderType.MARKET  # Default
        assert order.status == OrderStatus.OPEN  # Default
        assert order.quantity == 0
        assert order.filled_quantity == 0
        assert order.price == Decimal("0")
        assert order.avg_price == Decimal("0")

    def test_map_null_price(self):
        """Map null/empty price to None."""
        raw = {"price": None}
        mapping = DhanFieldMapping()
        assert mapping.map_price(raw) is None

        raw = {"price": ""}
        assert mapping.map_price(raw) is None

    def test_map_reject_reason(self):
        """Map reject reason."""
        raw = {"rejectReason": "Insufficient funds"}
        mapping = DhanFieldMapping()
        assert mapping.map_reject_reason(raw) == "Insufficient funds"


class TestUpstoxFieldMapping:
    """Test Upstox-specific field name mapping."""

    def test_map_complete_upstox_order(self):
        """Map a complete Upstox order response."""
        raw = {
            "order_id": "67890",
            "symbol": "TCS",
            "exchange": "NSE",
            "side": "SELL",
            "order_type": "MARKET",
            "status": "OPEN",
            "quantity": 5,
            "filled_quantity": 0,
            "price": "0",
            "avg_price": "0",
            "reject_reason": "",
        }
        mapping = UpstoxFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert order.order_id == "67890"
        assert order.symbol == "TCS"
        assert order.exchange == "NSE"
        assert order.side == Side.SELL
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.OPEN
        assert order.quantity == 5
        assert order.filled_quantity == 0

    def test_map_buy_order(self):
        """Map a BUY order."""
        raw = {
            "order_id": "11111",
            "symbol": "INFY",
            "side": "BUY",
            "order_type": "LIMIT",
            "status": "COMPLETE",
            "quantity": 10,
            "filled_quantity": 10,
            "price": "1500.00",
            "avg_price": "1498.50",
        }
        mapping = UpstoxFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.FILLED
        assert order.price == Decimal("1500.00")
        assert order.avg_price == Decimal("1498.50")

    def test_map_sl_alias(self):
        """Map SL to STOP_LOSS."""
        raw = {"order_type": "SL"}
        mapping = UpstoxFieldMapping()
        ot = mapping.map_order_type(raw)
        assert ot == "STOP_LOSS"

    def test_map_slm_alias(self):
        """Map SLM to STOP_LOSS_MARKET."""
        raw = {"order_type": "SLM"}
        mapping = UpstoxFieldMapping()
        ot = mapping.map_order_type(raw)
        assert ot == "STOP_LOSS_MARKET"

    def test_map_avg_price_alternate_key(self):
        """Map avg_price from alternate key (average_price)."""
        raw = {"average_price": "1234.56"}
        mapping = UpstoxFieldMapping()
        assert mapping.map_avg_price(raw) == "1234.56"

    def test_map_empty_fields(self):
        """Map empty dict to default values."""
        raw = {}
        mapping = UpstoxFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert order.order_id == ""
        assert order.symbol == ""
        assert order.exchange == "NSE"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.OPEN
        assert order.quantity == 0
        assert order.filled_quantity == 0

    def test_map_null_price(self):
        """Map null/empty price to None."""
        raw = {"price": None}
        mapping = UpstoxFieldMapping()
        assert mapping.map_price(raw) is None

        raw = {"price": ""}
        assert mapping.map_price(raw) is None


class TestBackwardCompatibility:
    """Test that existing code continues to work without changes."""

    def test_default_mapping_is_dhan(self):
        """Without field_mapping parameter, should use Dhan defaults."""
        raw = {
            "orderId": "123",
            "tradingSymbol": "INFY",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "orderStatus": "OPEN",
            "quantity": 10,
            "filledQty": 0,
            "price": "1500.00",
        }
        # No field_mapping parameter - should use Dhan defaults
        order = Order.from_broker_dict(raw)

        assert order.order_id == "123"
        assert order.symbol == "INFY"
        assert order.exchange == "NSE_EQ"
        assert order.side == Side.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.OPEN

    def test_exchange_resolver_still_works(self):
        """exchange_resolver parameter should still work."""
        raw = {
            "orderId": "456",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_FNO",
            "transactionType": "SELL",
            "orderType": "MARKET",
            "orderStatus": "COMPLETE",
            "quantity": 25,
            "filledQty": 25,
        }

        def mock_resolver(exchange: str) -> str:
            return f"Resolved:{exchange}"

        order = Order.from_broker_dict(raw, exchange_resolver=mock_resolver)

        assert order.order_id == "456"
        assert order.exchange == "Resolved:NSE_FNO"

    def test_existing_dhan_tests_still_pass(self):
        """Verify the old Dhan-style dict format still works."""
        # This is the format used in existing tests
        raw = {
            "orderId": "test-123",
            "tradingSymbol": "TEST",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "orderStatus": "COMPLETE",
            "quantity": 100,
            "filledQty": 100,
            "price": "100.00",
            "averagePrice": "100.00",
        }
        order = Order.from_broker_dict(raw)

        assert order.order_id == "test-123"
        assert order.symbol == "TEST"
        assert order.quantity == 100
        assert order.filled_quantity == 100


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_order_type_defaults_to_market(self):
        """Invalid order type should default to MARKET."""
        raw = {"orderType": "INVALID_TYPE"}
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)
        assert order.order_type == OrderType.MARKET

    def test_invalid_status_normalized(self):
        """Invalid status should be normalized."""
        raw = {"orderStatus": "UNKNOWN_STATUS"}
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)
        # OrderStatus.normalize should handle this
        assert order.status is not None

    def test_negative_quantity(self):
        """Negative quantity should be handled (though invalid)."""
        raw = {"quantity": -10}
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)
        assert order.quantity == -10  # Let validation catch this

    def test_decimal_prices(self):
        """Prices should be parsed as Decimal."""
        raw = {
            "price": "1234.5678",
            "averagePrice": "1234.5600",
        }
        mapping = DhanFieldMapping()
        order = Order.from_broker_dict(raw, field_mapping=mapping)

        assert isinstance(order.price, Decimal)
        assert order.price == Decimal("1234.5678")
        assert order.avg_price == Decimal("1234.5600")
