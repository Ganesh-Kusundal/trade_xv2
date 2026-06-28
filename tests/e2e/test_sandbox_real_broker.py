"""E2E: Sandbox-based tests with REAL broker APIs.

These tests run against Dhan/Upstox SANDBOX environments (not production).
They verify the complete flow: CLI → Service → Gateway → Real Broker API → Response.

Requirements:
- Dhan sandbox credentials in .env.local:
  DHAN_SANDBOX_CLIENT_ID=...
  DHAN_SANDBOX_ACCESS_TOKEN=...

- Marked with @pytest.mark.sandbox to skip in regular CI

Usage:
    ./venv/bin/python -m pytest tests/e2e/test_sandbox_real_broker.py -v -k sandbox
"""
import contextlib
import os

import pytest


@pytest.mark.sandbox
class TestDhanSandboxE2E:
    """Test Dhan broker with REAL sandbox API (not mocked)."""

    @pytest.fixture
    def dhan_sandbox_gateway(self):
        """Create Dhan gateway with sandbox credentials."""
        from dotenv import load_dotenv

        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.gateway import BrokerGateway

        load_dotenv(".env.local")

        client_id = os.getenv("DHAN_SANDBOX_CLIENT_ID")
        access_token = os.getenv("DHAN_SANDBOX_ACCESS_TOKEN")

        if not client_id or not access_token:
            pytest.skip("Dhan sandbox credentials not configured")

        # Create sandbox connection
        conn = DhanConnection(
            client_id=client_id,
            access_token=access_token,
            is_sandbox=True,  # Use sandbox mode
        )

        # Create gateway
        gw = BrokerGateway(conn)
        gw.load_instruments()

        yield gw

        # Cleanup
        with contextlib.suppress(Exception):
            gw.close()

    def test_sandbox_quote_returns_real_data(self, dhan_sandbox_gateway):
        """Verify quote command returns REAL data from Dhan sandbox."""
        gw = dhan_sandbox_gateway

        # Get real quote from sandbox
        quote = gw.quote("RELIANCE", "NSE")

        # Verify it's real data (not mocked)
        assert quote is not None
        assert quote.symbol == "RELIANCE"
        assert quote.ltp > 0, "LTP should be positive real price"
        assert quote.volume >= 0, "Volume should be non-negative"
        print(f"✅ Real quote: RELIANCE LTP={quote.ltp}")

    def test_sandbox_place_and_cancel_order(self, dhan_sandbox_gateway):
        """Verify complete order lifecycle on Dhan sandbox."""
        gw = dhan_sandbox_gateway

        # Place order in sandbox (no real money)
        response = gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
            product_type="INTRADAY",
        )

        assert response.success is True
        assert response.order_id is not None
        order_id = response.order_id
        print(f"✅ Placed order: {order_id}")

        # Cancel the order
        cancel_response = gw.cancel_order(order_id)
        assert cancel_response.success is True
        print(f"✅ Cancelled order: {order_id}")

    def test_sandbox_get_positions(self, dhan_sandbox_gateway):
        """Verify positions query works on Dhan sandbox."""
        gw = dhan_sandbox_gateway

        positions = gw.get_positions()

        assert isinstance(positions, list)
        # May be empty if no positions
        for pos in positions:
            assert pos.symbol is not None
            assert pos.quantity is not None
        print(f"✅ Positions: {len(positions)} positions found")

    def test_sandbox_get_orderbook(self, dhan_sandbox_gateway):
        """Verify orderbook query works on Dhan sandbox."""
        gw = dhan_sandbox_gateway

        orders = gw.get_orderbook()

        assert isinstance(orders, list)
        # Verify structure
        for order in orders:
            assert order.order_id is not None
            assert order.symbol is not None
            assert order.side is not None
        print(f"✅ Orderbook: {len(orders)} orders found")

    def test_sandbox_get_balance(self, dhan_sandbox_gateway):
        """Verify balance query works on Dhan sandbox."""
        gw = dhan_sandbox_gateway

        balance = gw.get_funds()

        assert balance is not None
        assert balance.available_balance > 0
        print(f"✅ Balance: ₹{balance.available_balance:,.2f}")


@pytest.mark.sandbox
class TestUpstoxSandboxE2E:
    """Test Upstox broker with REAL sandbox API (not mocked)."""

    @pytest.fixture
    def upstox_sandbox_gateway(self):
        """Create Upstox gateway with sandbox credentials."""
        from brokers.upstox.settings import UpstoxSettings
        from dotenv import load_dotenv

        from brokers.upstox.broker import UpstoxBroker
        from brokers.upstox.gateway import UpstoxBrokerGateway

        load_dotenv(".env.local")

        api_key = os.getenv("UPSTOX_SANDBOX_API_KEY")
        access_token = os.getenv("UPSTOX_SANDBOX_ACCESS_TOKEN")

        if not api_key or not access_token:
            pytest.skip("Upstox sandbox credentials not configured")

        # Create sandbox settings
        settings = UpstoxSettings(
            api_key=api_key,
            api_secret="",  # Not needed for sandbox
            access_token=access_token,
            is_sandbox=True,
        )

        # Create broker and gateway
        broker = UpstoxBroker(settings)
        gw = UpstoxBrokerGateway(broker)
        gw.load_instruments()

        yield gw

        # Cleanup
        with contextlib.suppress(Exception):
            gw.close()

    def test_sandbox_quote_returns_real_data(self, upstox_sandbox_gateway):
        """Verify quote command returns REAL data from Upstox sandbox."""
        gw = upstox_sandbox_gateway

        # Get real quote from sandbox
        quote = gw.quote("RELIANCE", "NSE")

        # Verify it's real data (not mocked)
        assert quote is not None
        assert quote.symbol == "RELIANCE"
        assert quote.ltp > 0, "LTP should be positive real price"
        print(f"✅ Real quote: RELIANCE LTP={quote.ltp}")

    def test_sandbox_place_and_cancel_order(self, upstox_sandbox_gateway):
        """Verify complete order lifecycle on Upstox sandbox."""
        gw = upstox_sandbox_gateway

        # Place order in sandbox (no real money)
        response = gw.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
            product_type="INTRADAY",
        )

        assert response.success is True
        assert response.order_id is not None
        order_id = response.order_id
        print(f"✅ Placed order: {order_id}")

        # Cancel the order
        cancel_response = gw.cancel_order(order_id)
        assert cancel_response.success is True
        print(f"✅ Cancelled order: {order_id}")


@pytest.mark.sandbox
class TestCrossBrokerParity:
    """Test that all brokers return EQUIVALENT data structures."""

    @pytest.fixture
    def dhan_sandbox(self):
        """Create Dhan sandbox gateway."""
        from dotenv import load_dotenv

        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.gateway import BrokerGateway

        load_dotenv(".env.local")

        client_id = os.getenv("DHAN_SANDBOX_CLIENT_ID")
        access_token = os.getenv("DHAN_SANDBOX_ACCESS_TOKEN")

        if not client_id or not access_token:
            pytest.skip("Dhan sandbox credentials not configured")

        conn = DhanConnection(
            client_id=client_id,
            access_token=access_token,
            is_sandbox=True,
        )

        gw = BrokerGateway(conn)
        gw.load_instruments()

        yield gw

        with contextlib.suppress(Exception):
            gw.close()

    @pytest.fixture
    def upstox_sandbox(self):
        """Create Upstox sandbox gateway."""
        from brokers.upstox.settings import UpstoxSettings
        from dotenv import load_dotenv

        from brokers.upstox.broker import UpstoxBroker
        from brokers.upstox.gateway import UpstoxBrokerGateway

        load_dotenv(".env.local")

        api_key = os.getenv("UPSTOX_SANDBOX_API_KEY")
        access_token = os.getenv("UPSTOX_SANDBOX_ACCESS_TOKEN")

        if not api_key or not access_token:
            pytest.skip("Upstox sandbox credentials not configured")

        settings = UpstoxSettings(
            api_key=api_key,
            api_secret="",
            access_token=access_token,
            is_sandbox=True,
        )

        broker = UpstoxBroker(settings)
        gw = UpstoxBrokerGateway(broker)
        gw.load_instruments()

        yield gw

        with contextlib.suppress(Exception):
            gw.close()

    def test_quote_returns_equivalent_schema(self, dhan_sandbox, upstox_sandbox):
        """All brokers should return Quote with same fields and types."""
        dhan_quote = dhan_sandbox.quote("RELIANCE", "NSE")
        upstox_quote = upstox_sandbox.quote("RELIANCE", "NSE")

        # Verify both have required fields
        for quote in [dhan_quote, upstox_quote]:
            assert hasattr(quote, 'ltp')
            assert hasattr(quote, 'symbol')
            assert hasattr(quote, 'volume')
            assert isinstance(quote.ltp, (int, float))
            assert quote.ltp > 0

        # Verify symbols match
        assert dhan_quote.symbol == upstox_quote.symbol == "RELIANCE"
        print("✅ Schema parity: Both brokers return equivalent Quote structures")

    def test_place_order_returns_equivalent_response(self, dhan_sandbox, upstox_sandbox):
        """All brokers should return OrderResponse with same fields."""
        dhan_response = dhan_sandbox.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        upstox_response = upstox_sandbox.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            order_type="MARKET",
        )

        # Verify both have required fields
        for response in [dhan_response, upstox_response]:
            assert hasattr(response, 'success')
            assert hasattr(response, 'order_id')
            assert response.success is True
            assert response.order_id is not None

        # Cancel both orders
        dhan_sandbox.cancel_order(dhan_response.order_id)
        upstox_sandbox.cancel_order(upstox_response.order_id)

        print("✅ OrderResponse parity: Both brokers return equivalent responses")
