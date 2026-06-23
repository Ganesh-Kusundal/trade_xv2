"""Tests for MarketDataAdapter.

Covers:
- LTP fetching with successful response
- LTP fetching with missing data
- Quote fetching with full OHLCV
- Quote fetching with missing data
- Depth fetching with order book
- Depth fetching with empty response
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain import MarketDepth, Quote
from brokers.upstox.adapters.market_data_adapter import MarketDataAdapter


@pytest.fixture
def mock_broker():
    """Create a mock broker with market_data_v2 client."""
    broker = MagicMock()
    broker.market_data_v2 = MagicMock()
    return broker


@pytest.fixture
def adapter(mock_broker):
    """Create MarketDataAdapter with mock broker."""
    return MarketDataAdapter(mock_broker)


class TestMarketDataAdapterLTP:
    """Test LTP fetching operations."""

    def test_ltp_success(self, adapter, mock_broker):
        """LTP returns correct price from API response."""
        mock_broker.market_data_v2.get_ltp.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "last_price": 2500.50,
                    "instrument_key": "NSE_EQ|RELIANCE",
                }
            }
        }

        result = adapter.get_ltp("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert result == Decimal("2500.5000")
        mock_broker.market_data_v2.get_ltp.assert_called_once_with(["NSE_EQ|RELIANCE"])

    def test_ltp_missing_data_returns_zero(self, adapter, mock_broker):
        """LTP returns Decimal(0) when data is missing."""
        mock_broker.market_data_v2.get_ltp.return_value = {"data": {}}

        result = adapter.get_ltp("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert result == Decimal("0")

    def test_ltp_no_last_price_field(self, adapter, mock_broker):
        """LTP returns Decimal(0) when last_price field missing."""
        mock_broker.market_data_v2.get_ltp.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "instrument_key": "NSE_EQ|RELIANCE",
                }
            }
        }

        result = adapter.get_ltp("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert result == Decimal("0")


class TestMarketDataAdapterQuote:
    """Test Quote fetching operations."""

    def test_quote_success_with_ohlc(self, adapter, mock_broker):
        """Quote returns full OHLCV data."""
        mock_broker.market_data_v2.get_quote.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "last_price": 2500.50,
                    "net_change": 50.25,
                    "volume": 1000000,
                    "ohlc": {
                        "open": 2480.00,
                        "high": 2520.00,
                        "low": 2470.00,
                        "close": 2450.00,
                    },
                }
            }
        }

        result = adapter.get_quote("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("2500.5000")
        assert result.open == Decimal("2480.0000")
        assert result.high == Decimal("2520.0000")
        assert result.low == Decimal("2470.0000")
        assert result.close == Decimal("2450.0000")
        assert result.volume == 1000000
        assert result.change == Decimal("50.2500")

    def test_quote_missing_data_returns_empty(self, adapter, mock_broker):
        """Quote returns empty Quote when data missing."""
        mock_broker.market_data_v2.get_quote.return_value = {"data": {}}

        result = adapter.get_quote("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("0")

    def test_quote_missing_ohlc_defaults_zero(self, adapter, mock_broker):
        """Quote defaults OHLC to 0 when missing."""
        mock_broker.market_data_v2.get_quote.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "last_price": 2500.00,
                }
            }
        }

        result = adapter.get_quote("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert result.ltp == Decimal("2500.0000")
        assert result.open == Decimal("0")
        assert result.high == Decimal("0")
        assert result.low == Decimal("0")
        assert result.close == Decimal("0")


class TestMarketDataAdapterDepth:
    """Test Market Depth fetching operations."""

    def test_depth_success(self, adapter, mock_broker):
        """Depth returns MarketDepth with bid/ask levels."""
        mock_broker.market_data_v2.get_order_book.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "depth": {
                        "buy": [
                            {"price": 2500.00, "quantity": 100, "orders": 5},
                        ],
                        "sell": [
                            {"price": 2501.00, "quantity": 150, "orders": 3},
                        ],
                    }
                }
            }
        }

        result = adapter.get_depth("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert isinstance(result, MarketDepth)
        assert len(result.bids) == 1
        assert len(result.asks) == 1
        assert result.bids[0].price == Decimal("2500.0000")
        assert result.asks[0].price == Decimal("2501.0000")

    def test_depth_empty_response(self, adapter, mock_broker):
        """Depth returns empty MarketDepth when response empty."""
        mock_broker.market_data_v2.get_order_book.return_value = {"data": {}}

        result = adapter.get_depth("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert isinstance(result, MarketDepth)
        assert len(result.bids) == 0
        assert len(result.asks) == 0

    def test_depth_no_depth_field(self, adapter, mock_broker):
        """Depth returns empty MarketDepth when depth field missing."""
        mock_broker.market_data_v2.get_order_book.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "instrument_key": "NSE_EQ|RELIANCE",
                }
            }
        }

        result = adapter.get_depth("RELIANCE", "NSE", "NSE_EQ|RELIANCE")

        assert isinstance(result, MarketDepth)
        assert len(result.bids) == 0
