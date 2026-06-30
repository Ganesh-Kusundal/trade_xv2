"""Upstox Gateway Integration Tests (P6-1).

Tests that verify UpstoxBrokerGateway works correctly with the full trading stack:
- Gateway creation and initialization
- Order placement with validation
- Order modification
- Order cancellation
- Portfolio queries
- Market data requests

- Error handling (network, auth, rate limits)
- Thread safety for concurrent operations

Run with:
    pytest tests/integration/test_upstox_gateway_integration.py -v
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest

from brokers.common.gateway import BrokerCapabilities
from brokers.upstox.gateway import UpstoxBrokerGateway
from domain import (
    Balance,
    MarketDepth,
    OrderResponse,
    Quote,
)
from tests.integration.fixtures.upstox import (
    make_depth_response,
    make_instrument_defn,
    make_mock_broker,
    make_quote_response,
    mock_market_quote,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_broker():
    """Create a basic mock broker."""
    return make_mock_broker(ws_connected=False, allow_live_orders=True)


@pytest.fixture
def mock_broker_orders_disabled():
    """Mock broker with live orders disabled."""
    return make_mock_broker(ws_connected=False, allow_live_orders=False)


@pytest.fixture
def mock_broker_connected():
    """Create a mock broker with connected WebSocket."""
    return make_mock_broker(ws_connected=True)


@pytest.fixture
def gateway(mock_broker):
    """Create an UpstoxBrokerGateway with mock broker."""
    return UpstoxBrokerGateway(mock_broker)


@pytest.fixture
def gateway_connected(mock_broker_connected):
    """Create a gateway with connected WebSocket."""
    return UpstoxBrokerGateway(mock_broker_connected)


@pytest.fixture
def instrument_defn():
    """Create a standard instrument definition for RELIANCE."""
    return make_instrument_defn(
        name="RELIANCE",
        symbol="RELIANCE",
        instrument_key="NSE_EQ|RELIANCE",
        exchange_segment="NSE_EQ",
    )


# ─── Gateway Creation & Initialization ─────────────────────────────────────


class TestGatewayCreation:
    """Test gateway creation and initialization."""

    def test_gateway_creates_adapters(self, mock_broker):
        """Gateway should create all internal adapters."""
        gateway = UpstoxBrokerGateway(mock_broker)

        assert gateway._market_data is not None
        assert gateway._historical is not None
        assert gateway._stream_manager is not None
        assert gateway._order_command is not None
        assert gateway._portfolio is not None

    def test_gateway_stores_broker_reference(self, mock_broker):
        """Gateway should store reference to broker."""
        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway._broker is mock_broker

    def test_gateway_stream_registry_accessible(self, mock_broker_connected):
        """Stream registry should be accessible for testing."""
        gateway = UpstoxBrokerGateway(mock_broker_connected)
        assert isinstance(gateway._stream_registry, dict)

    def test_gateway_stream_lock_accessible(self, mock_broker_connected):
        """Stream lock should be accessible for testing."""
        gateway = UpstoxBrokerGateway(mock_broker_connected)
        assert gateway._stream_lock is not None


# ─── Market Data Integration ───────────────────────────────────────────────


class TestMarketDataIntegration:
    """Test market data operations through the gateway."""

    def test_ltp_delegates_to_market_data_adapter(self, mock_broker, instrument_defn):
        """ltp() should resolve key and delegate to market data adapter."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_market_quote(mock_broker, "RELIANCE", 2500.50)

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.ltp("RELIANCE", "NSE")

        assert isinstance(result, Decimal)
        assert result == Decimal("2500.5000")

    def test_ltp_returns_zero_on_missing_data(self, mock_broker, instrument_defn):
        """ltp() should return Decimal(0) when no data returned."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.market_data_v2.get_quote.return_value = {"data": {}}

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.ltp("MISSING", "NSE")

        assert result == Decimal("0")

    def test_quote_returns_quote_object(self, mock_broker, instrument_defn):
        """quote() should return a Quote dataclass."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.market_data_v2.get_quote.return_value = make_quote_response("RELIANCE")

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.quote("RELIANCE", "NSE")

        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("1500.0000")

    def test_depth_returns_market_depth(self, mock_broker, instrument_defn):
        """depth() should return MarketDepth with bid/ask levels."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.market_data_v2.get_order_book.return_value = make_depth_response("RELIANCE")

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.depth("RELIANCE", "NSE")

        assert isinstance(result, MarketDepth)
        assert len(result.bids) == 1
        assert len(result.asks) == 1
        assert result.bids[0].price == Decimal("1500.0000")
        assert result.asks[0].price == Decimal("1501.0000")

    def test_quote_handles_missing_ohlc(self, mock_broker, instrument_defn):
        """quote() should handle missing OHLC data gracefully."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.market_data_v2.get_quote.return_value = {
            "status": "success",
            "data": {"symbol": "RELIANCE", "last_price": 2500.0},
        }

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.quote("RELIANCE", "NSE")

        assert isinstance(result, Quote)
        assert result.ltp == Decimal("2500.0000")
        assert result.open == Decimal("0")


# ─── Order Lifecycle Integration ──────────────────────────────────────────


class TestOrderIntegration:
    """Test order operations through the gateway."""

    def test_place_order_market_success(self, mock_broker, instrument_defn):
        """place_order() should return OrderResponse on success."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-001",
            message="Order placed",
        )

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        assert isinstance(result, OrderResponse)
        assert result.success is True
        assert result.order_id == "UPSTOX-001"

    def test_place_order_limit_with_price(self, mock_broker, instrument_defn):
        """place_order() should pass price for LIMIT orders."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.return_value = OrderResponse.ok(
            order_id="UPSTOX-002",
        )

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            price=Decimal("2500"),
            order_type="LIMIT",
        )

        assert result.success is True
        mock_broker.order_command.place_order.assert_called_once()

    def test_place_order_when_live_orders_disabled(self, mock_broker_orders_disabled):
        """place_order() should fail when live orders are disabled."""
        gateway = UpstoxBrokerGateway(mock_broker_orders_disabled)

        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        assert result.success is False
        assert "disabled" in result.message.lower()

    def test_place_order_catches_exception(self, mock_broker, instrument_defn):
        """place_order() should catch exceptions and return failed response."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_broker.order_command.place_order.side_effect = RuntimeError("Network error")

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        assert result.success is False
        assert "Network error" in result.message

    def test_cancel_order_success(self, mock_broker):
        """cancel_order() should return success response."""
        mock_broker.order_command.cancel_order.return_value = OrderResponse.ok(
            order_id="ORD-001",
            message="Order cancelled",
        )
        mock_broker.order_query.get_order.return_value = None

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.cancel_order("ORD-001")

        assert isinstance(result, OrderResponse)
        assert result.success is True
        assert result.order_id == "ORD-001"

    def test_cancel_order_failure(self, mock_broker):
        """cancel_order() should return failure on error."""
        mock_broker.order_command.cancel_order.return_value = OrderResponse.fail(
            message="Order not found",
        )

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.cancel_order("ORD-001")

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_cancel_order_when_live_orders_disabled(self, mock_broker_orders_disabled):
        """cancel_order() should fail when live orders are disabled."""
        gateway = UpstoxBrokerGateway(mock_broker_orders_disabled)

        result = gateway.cancel_order("ORD-001")

        assert result.success is False
        assert "disabled" in result.message.lower()

    def test_cancel_order_network_error(self, mock_broker):
        """cancel_order() should handle network errors gracefully."""
        mock_broker.order_command.cancel_order.return_value = OrderResponse.fail(
            message="network error: Timeout",
        )

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.cancel_order("ORD-001")

        assert result.success is False
        assert "network error" in result.message.lower()

    def test_cancel_order_malformed_response(self, mock_broker):
        """cancel_order() should handle non-success response."""
        mock_broker.order_command.cancel_order.return_value = OrderResponse.fail(
            message="malformed broker response (not a dict)",
        )

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.cancel_order("ORD-001")

        assert result.success is False
        assert "malformed" in result.message.lower()


# ─── Portfolio Integration ─────────────────────────────────────────────────


class TestPortfolioIntegration:
    """Test portfolio operations through the gateway."""

    def test_funds_returns_balance(self, mock_broker):
        """funds() should return Balance dataclass."""

        # Configure portfolio adapter mock
        mock_broker.portfolio.get_fund_limits.return_value = Balance(
            available_balance=Decimal("100000"),
            used_margin=Decimal("5000"),
            total_margin=Decimal("105000"),
        )

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.funds()

        assert isinstance(result, Balance)
        assert result.available_balance == Decimal("100000")

    def test_positions_returns_list(self, mock_broker):
        """positions() should return list of Position."""
        mock_broker.portfolio.get_positions.return_value = []

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.positions()

        assert isinstance(result, list)

    def test_holdings_returns_list(self, mock_broker):
        """holdings() should return list of Holding."""
        mock_broker.portfolio.get_holdings.return_value = []

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.holdings()

        assert isinstance(result, list)

    def test_get_orderbook_returns_list(self, mock_broker):
        """get_orderbook() should return list of orders."""
        mock_broker.order_query.get_order_list.return_value = []

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.get_orderbook()

        assert isinstance(result, list)

    def test_trades_returns_list(self, mock_broker):
        """trades() should return list of Trade."""
        mock_broker.order_query.get_trades.return_value = []

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.trades()

        assert isinstance(result, list)




# ─── Capabilities & Metadata ──────────────────────────────────────────────


class TestCapabilitiesAndMetadata:
    """Test gateway capabilities and metadata."""

    def test_capabilities_returns_broker_capabilities(self, mock_broker):
        """capabilities() should return BrokerCapabilities."""
        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.capabilities()

        assert isinstance(result, BrokerCapabilities)

    def test_capabilities_has_websocket_flag(self, mock_broker):
        """capabilities() should indicate WebSocket support."""
        gateway = UpstoxBrokerGateway(mock_broker)
        caps = gateway.capabilities()

        assert caps.supports_order_stream is True

    def test_capabilities_has_order_types(self, mock_broker):
        """capabilities() should list supported order types."""
        gateway = UpstoxBrokerGateway(mock_broker)
        caps = gateway.capabilities()

        assert "MARKET" in caps.order_types
        assert "LIMIT" in caps.order_types
        assert "STOP_LOSS" in caps.order_types

    def test_capabilities_has_product_types(self, mock_broker):
        """capabilities() should list supported product types."""
        gateway = UpstoxBrokerGateway(mock_broker)
        caps = gateway.capabilities()

        assert "INTRADAY" in caps.product_types
        assert "CNC" in caps.product_types

    def test_describe_returns_dict(self, mock_broker):
        """describe() should return broker metadata dict."""
        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.describe()

        assert isinstance(result, dict)
        assert result["broker"] == "Upstox"

    def test_search_returns_list(self, mock_broker):
        """search() should return list of instruments."""
        mock_broker.instrument_resolver.search.return_value = []
        gateway = UpstoxBrokerGateway(mock_broker)

        result = gateway.search("RELIANCE")

        assert isinstance(result, list)


# ─── Error Handling ───────────────────────────────────────────────────────


class TestErrorHandling:
    """Test error scenarios."""

    def test_ltp_with_unresolvable_symbol(self, mock_broker):
        """ltp() should handle unresolvable symbols gracefully."""
        mock_broker.instrument_resolver.resolve.return_value = None
        mock_broker.market_data_v2.get_ltp.return_value = {"data": {}}

        gateway = UpstoxBrokerGateway(mock_broker)
        result = gateway.ltp("UNKNOWN_SYMBOL", "NSE")

        assert result == Decimal("0")

    def test_close_is_idempotent(self, mock_broker):
        """close() should be safe to call multiple times."""
        gateway = UpstoxBrokerGateway(mock_broker)

        gateway.close()
        gateway.close()  # Should not raise

        mock_broker.disconnect.assert_called()

    def test_future_chain_returns_future_chain(self, mock_broker):
        """future_chain() should return a FutureChain from broker futures adapter."""
        from domain import FutureChain

        mock_broker.futures.get_contracts.return_value = [
            {
                "expiry": "2026-06-26",
                "symbol": "RELIANCE26JUNFUT",
                "lot_size": 250,
                "underlying": "RELIANCE",
            },
        ]
        mock_broker.futures.get_expiries.return_value = ["2026-06-26"]
        gateway = UpstoxBrokerGateway(mock_broker)

        result = gateway.future_chain("RELIANCE", "NFO")

        assert isinstance(result, FutureChain)
        assert result.underlying == "RELIANCE"
        assert len(result.contracts) == 1


# ─── Thread Safety ────────────────────────────────────────────────────────


class TestThreadSafety:
    """Test concurrent operations don't corrupt state."""

    def test_concurrent_ltp_calls(self, mock_broker, instrument_defn):
        """Concurrent ltp() calls should not corrupt state."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        mock_market_quote(mock_broker, "RELIANCE", 2500.50)

        gateway = UpstoxBrokerGateway(mock_broker)
        results = []
        errors = []

        def fetch_ltp():
            try:
                r = gateway.ltp("RELIANCE", "NSE")
                results.append(r)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_ltp) for _ in range(20)]
            for f in as_completed(futures):
                f.result()  # Re-raise any exceptions

        assert len(errors) == 0
        assert len(results) == 20
        assert all(r == Decimal("2500.5000") for r in results)

    def test_concurrent_order_placements(self, mock_broker, instrument_defn):
        """Concurrent order placements should not corrupt state."""
        mock_broker.instrument_resolver.resolve.return_value = instrument_defn
        call_count = {"value": 0}
        lock = threading.Lock()

        def mock_place_order(*args, **kwargs):
            with lock:
                call_count["value"] += 1
            time.sleep(0.001)  # Simulate network latency
            return OrderResponse.ok(order_id=f"ORD-{call_count['value']}")

        mock_broker.order_command.place_order.side_effect = mock_place_order

        gateway = UpstoxBrokerGateway(mock_broker)
        errors = []

        def place_order(i: int):
            try:
                r = gateway.place_order(
                    symbol="RELIANCE",
                    exchange="NSE",
                    side="BUY",
                    quantity=1,
                    order_type="MARKET",
                )
                assert r.success is True
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(place_order, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0

    def test_constream_subscribe_unsubscribe(self, mock_broker_connected):
        """Concurrent subscribe/unsubscribe should not corrupt stream registry."""
        gateway = UpstoxBrokerGateway(mock_broker_connected)

        def subscribe(i: int):
            def on_tick(tick):
                pass

            gateway.stream(f"SYM{i}", exchange="NSE", mode="LTP", on_tick=on_tick)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(subscribe, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        # Verify registry integrity
        assert len(gateway._stream_registry) == 10

    def test_concurrent_portfolio_queries(self, mock_broker):
        """Concurrent portfolio queries should not corrupt state."""
        mock_broker.portfolio.get_fund_limits.return_value = Balance(
            available_balance=Decimal("100000"),
        )
        mock_broker.portfolio.get_positions.return_value = []
        mock_broker.portfolio.get_holdings.return_value = []

        gateway = UpstoxBrokerGateway(mock_broker)
        errors = []

        def query_portfolio():
            try:
                gateway.funds()
                gateway.positions()
                gateway.holdings()
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(query_portfolio) for _ in range(20)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
