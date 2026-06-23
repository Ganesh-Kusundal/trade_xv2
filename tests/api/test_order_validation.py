"""Tests for order request validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas import OrderRequest


class TestOrderRequestValidation:
    """Test comprehensive order validation."""

    def test_valid_market_order(self):
        """Market order should not require price or trigger_price."""
        order = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            order_type="MARKET",
            quantity=1,
            product_type="INTRADAY",
        )
        assert order.symbol == "RELIANCE"
        assert order.price is None
        assert order.trigger_price is None

    def test_valid_limit_order(self):
        """LIMIT order requires price."""
        order = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            order_type="LIMIT",
            quantity=1,
            price=2500.0,
        )
        assert order.price == 2500.0

    def test_limit_order_without_price_fails(self):
        """LIMIT order without price should fail validation."""
        with pytest.raises(ValidationError, match="price is required"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="LIMIT",
                quantity=1,
            )

    def test_valid_sl_order(self):
        """SL order requires both price and trigger_price."""
        order = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            order_type="SL",
            quantity=1,
            price=2550.0,
            trigger_price=2500.0,
        )
        assert order.price == 2550.0
        assert order.trigger_price == 2500.0

    def test_sl_order_without_trigger_price_fails(self):
        """SL order without trigger_price should fail."""
        with pytest.raises(ValidationError, match="trigger_price is required"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="SL",
                quantity=1,
                price=2550.0,
            )

    def test_valid_slm_order(self):
        """SL-M order requires trigger_price but not price."""
        order = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="SELL",
            order_type="SL-M",
            quantity=1,
            trigger_price=2450.0,
        )
        assert order.trigger_price == 2450.0
        assert order.price is None

    def test_invalid_exchange_fails(self):
        """Invalid exchange should fail validation."""
        with pytest.raises(ValidationError, match="exchange must be one of"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NYSE",  # Invalid for Indian broker
                transaction_type="BUY",
                order_type="MARKET",
                quantity=1,
            )

    def test_invalid_order_type_fails(self):
        """Invalid order type should fail validation."""
        with pytest.raises(ValidationError, match="order_type must be one of"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="STOP",  # Invalid
                quantity=1,
            )

    def test_invalid_transaction_type_fails(self):
        """Invalid transaction type should fail validation."""
        with pytest.raises(ValidationError, match="transaction_type must be BUY or SELL"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="LONG",  # Invalid
                order_type="MARKET",
                quantity=1,
            )

    def test_invalid_product_type_fails(self):
        """Invalid product type should fail validation."""
        with pytest.raises(ValidationError, match="product_type must be one of"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="MARKET",
                quantity=1,
                product_type="OPTIONS",  # Invalid
            )

    def test_negative_price_fails(self):
        """Negative price should fail validation."""
        with pytest.raises(ValidationError):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="LIMIT",
                quantity=1,
                price=-100.0,
            )

    def test_zero_quantity_fails(self):
        """Zero quantity should fail validation."""
        with pytest.raises(ValidationError):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="MARKET",
                quantity=0,
            )

    def test_empty_symbol_fails(self):
        """Empty symbol should fail validation."""
        with pytest.raises(ValidationError):
            OrderRequest(
                symbol="",
                exchange="NSE",
                transaction_type="BUY",
                order_type="MARKET",
                quantity=1,
            )

    def test_case_insensitive_values(self):
        """Validation should accept lowercase values and normalize to uppercase."""
        order = OrderRequest(
            symbol="reliance",
            exchange="nse",
            transaction_type="buy",
            order_type="limit",
            quantity=1,
            price=2500.0,
            product_type="intraday",
        )
        assert order.exchange == "NSE"
        assert order.transaction_type == "BUY"
        assert order.order_type == "LIMIT"
        assert order.product_type == "INTRADAY"

    def test_sl_buy_order_price_below_trigger_fails(self):
        """SL BUY: price must be >= trigger_price."""
        with pytest.raises(ValidationError, match="price must be >= trigger_price"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                order_type="SL",
                quantity=1,
                price=2450.0,  # Below trigger
                trigger_price=2500.0,
            )

    def test_sl_sell_order_price_above_trigger_fails(self):
        """SL SELL: price must be <= trigger_price."""
        with pytest.raises(ValidationError, match="price must be <= trigger_price"):
            OrderRequest(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="SELL",
                order_type="SL",
                quantity=1,
                price=2550.0,  # Above trigger
                trigger_price=2500.0,
            )
