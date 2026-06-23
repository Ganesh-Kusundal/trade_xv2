"""MarketDataGateway contract tests — verify all broker adapters conform to the ABC.

These tests ensure that every broker adapter (Dhan, Upstox, Paper) correctly
implements the frozen MarketDataGateway v1.0 contract. Any deviation (missing
method, wrong return type, incorrect schema) will fail fast.

Run with:
    pytest tests/integration/test_gateway_contract.py -v
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from domain import (
    Balance,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def paper_gateway():
    """Return a PaperGateway instance for contract testing."""
    from brokers.paper.paper_gateway import PaperGateway
    return PaperGateway()


@pytest.fixture
def all_abstract_methods():
    """Return set of all abstract method names from MarketDataGateway."""
    return MarketDataGateway.__abstractmethods__.copy()


# ---------------------------------------------------------------------------
# Contract: All abstract methods must be implemented
# ---------------------------------------------------------------------------


class TestGatewayContract:
    """Verify all broker adapters implement MarketDataGateway."""

    def test_paper_gateway_is_subclass(self):
        """PaperGateway must extend MarketDataGateway."""
        from brokers.paper.paper_gateway import PaperGateway
        assert issubclass(PaperGateway, MarketDataGateway)

    def test_dhan_gateway_is_subclass(self):
        """Dhan BrokerGateway must extend MarketDataGateway."""
        from brokers.dhan.gateway import BrokerGateway
        assert issubclass(BrokerGateway, MarketDataGateway)

    def test_upstox_gateway_is_subclass(self):
        """Upstox UpstoxBrokerGateway must extend MarketDataGateway."""
        from brokers.upstox.gateway import UpstoxBrokerGateway
        assert issubclass(UpstoxBrokerGateway, MarketDataGateway)

    def test_no_abstract_methods_remaining(self, paper_gateway):
        """PaperGateway must have implemented all abstract methods.

        Since paper_gateway instantiated successfully, Python's ABC mechanism
        already verified all abstract methods are implemented. This test just
        documents that fact.
        """
        # If any abstract method remained unimplemented, PaperGateway would
        # be abstract and the fixture would have failed to instantiate.
        # The fact we have a paper_gateway instance proves full implementation.
        assert paper_gateway is not None

    def test_all_methods_callable(self, paper_gateway):
        """All gateway methods must be callable (not just present)."""
        methods = [
            "history", "quote", "ltp", "depth", "option_chain", "future_chain",
            "stream", "ltp_batch", "quote_batch", "history_batch",
            "place_order", "cancel_order", "get_orderbook", "get_trade_book",
            "positions", "holdings", "funds", "trades",
            "search", "load_instruments", "capabilities", "describe", "close",
        ]
        for method_name in methods:
            method = getattr(paper_gateway, method_name)
            assert callable(method), f"{method_name} is not callable"


# ---------------------------------------------------------------------------
# Contract: Return type validation
# ---------------------------------------------------------------------------


class TestReturnTypes:
    """Verify methods return correct types."""

    def test_quote_returns_quote(self, paper_gateway):
        """quote() must return a Quote instance."""
        quote = paper_gateway.quote("RELIANCE", "NSE")
        assert isinstance(quote, Quote), f"Expected Quote, got {type(quote)}"

    def test_ltp_returns_decimal(self, paper_gateway):
        """ltp() must return a Decimal."""
        ltp = paper_gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal), f"Expected Decimal, got {type(ltp)}"

    def test_depth_returns_market_depth(self, paper_gateway):
        """depth() must return a MarketDepth instance."""
        depth = paper_gateway.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth), f"Expected MarketDepth, got {type(depth)}"

    def test_place_order_returns_order_response(self, paper_gateway):
        """place_order() must return an OrderResponse."""
        response = paper_gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )
        assert isinstance(response, OrderResponse), (
            f"Expected OrderResponse, got {type(response)}"
        )

    def test_positions_returns_list(self, paper_gateway):
        """positions() must return a list."""
        positions = paper_gateway.positions()
        assert isinstance(positions, list), f"Expected list, got {type(positions)}"
        if positions:
            assert isinstance(positions[0], Position), (
                f"Expected list[Position], got {type(positions[0])}"
            )

    def test_holdings_returns_list(self, paper_gateway):
        """holdings() must return a list."""
        holdings = paper_gateway.holdings()
        assert isinstance(holdings, list), f"Expected list, got {type(holdings)}"
        if holdings:
            assert isinstance(holdings[0], Holding), (
                f"Expected list[Holding], got {type(holdings[0])}"
            )

    def test_funds_returns_balance(self, paper_gateway):
        """funds() must return a Balance instance."""
        funds = paper_gateway.funds()
        assert isinstance(funds, Balance), f"Expected Balance, got {type(funds)}"

    def test_get_orderbook_returns_list_of_orders(self, paper_gateway):
        """get_orderbook() must return list[Order]."""
        orderbook = paper_gateway.get_orderbook()
        assert isinstance(orderbook, list), f"Expected list, got {type(orderbook)}"
        if orderbook:
            assert isinstance(orderbook[0], Order), (
                f"Expected list[Order], got {type(orderbook[0])}"
            )

    def test_get_trade_book_returns_list_of_trades(self, paper_gateway):
        """get_trade_book() must return list[Trade]."""
        trades = paper_gateway.get_trade_book()
        assert isinstance(trades, list), f"Expected list, got {type(trades)}"
        if trades:
            assert isinstance(trades[0], Trade), (
                f"Expected list[Trade], got {type(trades[0])}"
            )

    def test_capabilities_returns_broker_capabilities(self, paper_gateway):
        """capabilities() must return BrokerCapabilities."""
        caps = paper_gateway.capabilities()
        assert isinstance(caps, BrokerCapabilities), (
            f"Expected BrokerCapabilities, got {type(caps)}"
        )

    def test_describe_returns_dict(self, paper_gateway):
        """describe() must return a dict."""
        desc = paper_gateway.describe()
        assert isinstance(desc, dict), f"Expected dict, got {type(desc)}"

    def test_search_returns_list(self, paper_gateway):
        """search() must return a list."""
        results = paper_gateway.search("RELIANCE")
        assert isinstance(results, list), f"Expected list, got {type(results)}"


# ---------------------------------------------------------------------------
# Contract: Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Verify return value schemas match specification."""

    def test_history_returns_dataframe_with_canonical_columns(self, paper_gateway):
        """history() must return DataFrame with canonical schema."""
        df = paper_gateway.history("RELIANCE", timeframe="1D", lookback_days=7)
        assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"

        required_columns = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_columns:
            assert col in df.columns, f"Missing required column: {col}"

    def test_history_symbol_column_present(self, paper_gateway):
        """history() DataFrame must have 'symbol' column."""
        df = paper_gateway.history("RELIANCE", timeframe="1D", lookback_days=7)
        if not df.empty:
            assert "symbol" in df.columns, "Missing 'symbol' column"
            assert df["symbol"].iloc[0] == "RELIANCE"

    def test_history_exchange_column_present(self, paper_gateway):
        """history() DataFrame must have 'exchange' column."""
        df = paper_gateway.history("RELIANCE", timeframe="1D", lookback_days=7)
        if not df.empty:
            assert "exchange" in df.columns, "Missing 'exchange' column"

    def test_quote_has_required_fields(self, paper_gateway):
        """Quote must have all required fields."""
        quote = paper_gateway.quote("RELIANCE", "NSE")
        required_fields = ["symbol", "ltp", "open", "high", "low", "close", "volume"]
        for field in required_fields:
            assert hasattr(quote, field), f"Quote missing field: {field}"

    def test_market_depth_has_bids_and_asks(self, paper_gateway):
        """MarketDepth must have bids and asks."""
        depth = paper_gateway.depth("RELIANCE", "NSE")
        assert hasattr(depth, "bids"), "MarketDepth missing 'bids'"
        assert hasattr(depth, "asks"), "MarketDepth missing 'asks'"
        assert isinstance(depth.bids, list), "bids must be a list"
        assert isinstance(depth.asks, list), "asks must be a list"

    def test_balance_has_required_fields(self, paper_gateway):
        """Balance must have required fields."""
        funds = paper_gateway.funds()
        required_fields = ["available_balance", "used_margin", "total_margin"]
        for field in required_fields:
            assert hasattr(funds, field), f"Balance missing field: {field}"

    def test_order_response_has_required_fields(self, paper_gateway):
        """OrderResponse must have required fields."""
        response = paper_gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )
        required_fields = ["success", "order_id", "message"]
        for field in required_fields:
            assert hasattr(response, field), f"OrderResponse missing field: {field}"


# ---------------------------------------------------------------------------
# Contract: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify error handling conforms to contract."""

    def test_cancel_invalid_order_returns_false(self, paper_gateway):
        """cancel_order() must return False for invalid order_id."""
        result = paper_gateway.cancel_order("INVALID_ORDER_ID")
        assert result is False, "cancel_order should return False for invalid order"

    def test_place_order_with_invalid_side_raises(self, paper_gateway):
        """place_order() with invalid side should raise ValueError."""
        with pytest.raises((ValueError, KeyError)):
            paper_gateway.place_order(
                symbol="RELIANCE",
                side="INVALID",
                quantity=1,
                order_type="MARKET",
            )

    def test_ltp_missing_symbol_handles_gracefully(self, paper_gateway):
        """ltp() with missing symbol should not crash."""
        # Paper gateway returns Decimal("0") for unknown symbols
        ltp = paper_gateway.ltp("UNKNOWN_SYMBOL", "NSE")
        assert isinstance(ltp, Decimal)


# ---------------------------------------------------------------------------
# Contract: Batch operations
# ---------------------------------------------------------------------------


class TestBatchOperations:
    """Verify batch operation contracts."""

    def test_ltp_batch_returns_dict(self, paper_gateway):
        """ltp_batch() must return dict[str, Decimal]."""
        result = paper_gateway.ltp_batch(["RELIANCE", "TCS"], "NSE")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        for symbol, ltp in result.items():
            assert isinstance(symbol, str), f"Keys must be str, got {type(symbol)}"
            assert isinstance(ltp, Decimal), f"Values must be Decimal, got {type(ltp)}"

    def test_quote_batch_returns_dict(self, paper_gateway):
        """quote_batch() must return dict[str, Quote]."""
        result = paper_gateway.quote_batch(["RELIANCE", "TCS"], "NSE")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        for symbol, quote in result.items():
            assert isinstance(symbol, str), f"Keys must be str, got {type(symbol)}"
            assert isinstance(quote, Quote), f"Values must be Quote, got {type(quote)}"

    def test_history_batch_returns_dataframe(self, paper_gateway):
        """history_batch() must return DataFrame with 'symbol' column."""
        df = paper_gateway.history_batch(["RELIANCE", "TCS"], timeframe="1D", lookback_days=7)
        assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
        if not df.empty:
            assert "symbol" in df.columns, "Missing 'symbol' column in batch result"


# ---------------------------------------------------------------------------
# Contract: Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Verify lifecycle methods."""

    def test_close_is_idempotent(self, paper_gateway):
        """close() must be safe to call multiple times."""
        paper_gateway.close()
        paper_gateway.close()  # Should not raise

    def test_describe_has_name_and_version(self, paper_gateway):
        """describe() must include name and version."""
        desc = paper_gateway.describe()
        assert "name" in desc, "describe() missing 'name'"
        assert "version" in desc, "describe() missing 'version'"

    def test_capabilities_has_required_fields(self, paper_gateway):
        """capabilities() must include key capability flags."""
        caps = paper_gateway.capabilities()
        required_fields = [
            "websocket", "parallel_history", "max_batch_size",
            "rate_limit_per_second", "rate_limit_per_minute",
        ]
        for field in required_fields:
            assert hasattr(caps, field), f"BrokerCapabilities missing field: {field}"
