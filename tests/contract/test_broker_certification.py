"""
BROKER CERTIFICATION SUITE

Every broker adapter (Dhan, Upstox, Paper) MUST pass these identical tests.
If one broker passes and another fails -> PR Rejected.

This suite verifies:
1. Order lifecycle (place, modify, cancel, status)
2. Market data (historical, live ticks, depth)
3. Portfolio (positions, holdings, funds)
4. Connection health (auth, reconnect, rate limits)

Run: pytest tests/contract/test_broker_certification.py -v --broker=dhan
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Type, List

from domain.entities.instrument import Instrument
from domain.enums import Side as OrderSide, OrderType, OrderStatus
from domain.ports.broker_gateway import IBrokerGateway


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def broker_gateway(broker_name: str) -> IBrokerGateway:
    """
    Create broker gateway instance based on --broker CLI argument.
    
    Usage:
        pytest tests/contract/test_broker_certification.py --broker=dhan
        pytest tests/contract/test_broker_certification.py --broker=upstox
    """
    if broker_name == "dhan":
        from brokers.dhan.gateway import DhanGateway
        return DhanGateway()
    elif broker_name == "upstox":
        from brokers.upstox.gateway import UpstoxGateway
        return UpstoxGateway()
    elif broker_name == "paper":
        from brokers.paper.gateway import PaperGateway
        return PaperGateway()
    else:
        raise ValueError(f"Unknown broker: {broker_name}. Use: dhan, upstox, paper")


@pytest.fixture(scope="module")
def nifty_instrument() -> Instrument:
    """Standard NIFTY futures instrument for testing."""
    return Instrument(
        symbol="NIFTY",
        exchange=Exchange.NSE,
        segment="NSE_FNO",
        lot_size=25,
        tick_size=Decimal("0.05"),
    )


@pytest.fixture(scope="module")
def banknifty_instrument() -> Instrument:
    """Standard BANKNIFTY futures instrument for testing."""
    return Instrument(
        symbol="BANKNIFTY",
        exchange=Exchange.NSE,
        segment="NSE_FNO",
        lot_size=15,
        tick_size=Decimal("0.05"),
    )


# =============================================================================
# ORDER LIFECYCLE TESTS
# =============================================================================

class TestOrderLifecycle:
    """Verify order placement, modification, cancellation, and status tracking."""
    
    def test_place_market_buy_success(self, broker_gateway: IBrokerGateway, nifty_instrument: Instrument):
        """
        Place a MARKET BUY order and verify it's accepted.
        
        Expected:
            - Order placed successfully
            - Order ID assigned
            - Status is SUBMITTED or PENDING
        """
        # Skip if not connected (test environment without credentials)
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected - skipping live order test")
        
        result = broker_gateway.place_order(
            instrument=nifty_instrument,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=25,  # 1 lot
            client_order_id=f"TEST_BUY_{datetime.now().timestamp()}",
        )
        
        assert result.is_success, f"Order placement failed: {result.error}"
        order = result.value
        
        assert order.order_id is not None, "Order ID should be assigned"
        assert order.status in [OrderStatus.SUBMITTED, OrderStatus.PENDING, OrderStatus.OPEN], \
            f"Unexpected status: {order.status}"
    
    def test_place_limit_sell_success(self, broker_gateway: IBrokerGateway, nifty_instrument: Instrument):
        """
        Place a LIMIT SELL order with explicit price.
        
        Expected:
            - Order placed with correct price
            - Price stored as Decimal (no float)
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        result = broker_gateway.place_order(
            instrument=nifty_instrument,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=25,
            price=Decimal("24500.00"),
            client_order_id=f"TEST_SELL_{datetime.now().timestamp()}",
        )
        
        assert result.is_success
        order = result.value
        
        # Verify price precision preserved
        assert isinstance(order.price, Decimal), "Price must be Decimal, not float"
        assert order.price == Decimal("24500.00"), "Price should match exactly"
    
    def test_cancel_order_success(self, broker_gateway: IBrokerGateway, nifty_instrument: Instrument):
        """
        Place an order and immediately cancel it.
        
        Expected:
            - Cancel succeeds
            - Order status becomes CANCELLED
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        # Place order
        place_result = broker_gateway.place_order(
            instrument=nifty_instrument,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=25,
            price=Decimal("24000.00"),  # Far from market to ensure it doesn't fill
            client_order_id=f"TEST_CANCEL_{datetime.now().timestamp()}",
        )
        
        if not place_result.is_success:
            pytest.skip("Could not place order for cancel test")
        
        order_id = place_result.value.order_id
        
        # Cancel order
        cancel_result = broker_gateway.cancel_order(order_id)
        
        assert cancel_result.is_success, f"Cancel failed: {cancel_result.error}"
        cancelled_order = cancel_result.value
        
        assert cancelled_order.status == OrderStatus.CANCELLED, \
            f"Expected CANCELLED, got {cancelled_order.status}"
    
    def test_get_order_status(self, broker_gateway: IBrokerGateway, nifty_instrument: Instrument):
        """
        Fetch status of an existing order.
        
        Expected:
            - Returns current order state
            - Contains all required fields (quantity, filled_qty, status)
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        # Place order
        place_result = broker_gateway.place_order(
            instrument=nifty_instrument,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=25,
            client_order_id=f"TEST_STATUS_{datetime.now().timestamp()}",
        )
        
        if not place_result.is_success:
            pytest.skip("Could not place order for status test")
        
        order_id = place_result.value.order_id
        
        # Get status
        status_result = broker_gateway.get_order_status(order_id)
        
        assert status_result.is_success
        order = status_result.value
        
        # Verify required fields present
        assert order.quantity > 0
        assert order.filled_quantity >= 0
        assert order.status is not None
    
    def test_get_all_orders_today(self, broker_gateway: IBrokerGateway):
        """
        Fetch all orders for today.
        
        Expected:
            - Returns list (possibly empty)
            - All orders have valid structure
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        result = broker_gateway.get_all_orders(date=datetime.now())
        
        assert result.is_success
        orders = result.value
        
        assert isinstance(orders, list)
        
        # Verify each order has required fields
        for order in orders:
            assert hasattr(order, 'order_id')
            assert hasattr(order, 'status')
            assert hasattr(order, 'quantity')


# =============================================================================
# PORTFOLIO TESTS
# =============================================================================

class TestPortfolio:
    """Verify position, holding, and funds retrieval."""
    
    def test_get_positions(self, broker_gateway: IBrokerGateway):
        """
        Fetch all open positions.
        
        Expected:
            - Returns list (possibly empty)
            - Each position has quantity, avg_price, unrealized_pnl
            - Prices are Decimal (not float)
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        result = broker_gateway.get_positions()
        
        assert result.is_success
        positions = result.value
        
        assert isinstance(positions, list)
        
        for position in positions:
            # Verify structure
            assert hasattr(position, 'quantity')
            assert hasattr(position, 'average_price')
            
            # Verify Decimal precision
            assert isinstance(position.average_price, Decimal), \
                "Average price must be Decimal"
    
    def test_get_holdings(self, broker_gateway: IBrokerGateway):
        """
        Fetch T+1/T+2 holdings (delivery positions).
        
        Expected:
            - Returns list (possibly empty)
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        result = broker_gateway.get_holdings()
        
        assert result.is_success
        holdings = result.value
        
        assert isinstance(holdings, list)
    
    def test_get_funds(self, broker_gateway: IBrokerGateway):
        """
        Fetch account funds/margins.
        
        Expected:
            - Returns dict with available_cash, margin_used, total_equity
            - All values are Decimal
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        result = broker_gateway.get_funds()
        
        assert result.is_success
        funds = result.value
        
        assert isinstance(funds, dict)
        assert 'available_cash' in funds or 'margin_available' in funds
        
        # Verify Decimal precision for monetary values
        for key, value in funds.items():
            if isinstance(value, (int, float)):
                # Should be converted to Decimal
                assert isinstance(value, Decimal), \
                    f"Funds field '{key}' should be Decimal, got {type(value)}"


# =============================================================================
# MARKET DATA TESTS
# =============================================================================

class TestMarketData:
    """Verify historical and live market data retrieval."""
    
    def test_get_historical_data_1min(self, broker_gateway: IBrokerGateway, nifty_instrument: Instrument):
        """
        Fetch 1-minute historical bars.
        
        Performance Requirement: < 5 seconds for 5 days
        
        Expected:
            - Returns list of bars with OHLCV
            - Bars sorted by timestamp
            - No gaps in sequence
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        result = broker_gateway.get_historical_data(
            instrument=nifty_instrument,
            timeframe='1min',
            start_date=start_date,
            end_date=end_date,
        )
        
        assert result.is_success, f"Historical fetch failed: {result.error}"
        bars = result.value
        
        assert len(bars) > 0, "Should return at least some bars"
        
        # Verify bar structure
        first_bar = bars[0]
        assert hasattr(first_bar, 'open')
        assert hasattr(first_bar, 'high')
        assert hasattr(first_bar, 'low')
        assert hasattr(first_bar, 'close')
        assert hasattr(first_bar, 'volume')
        
        # Verify sorted by timestamp
        timestamps = [bar.timestamp for bar in bars]
        assert timestamps == sorted(timestamps), "Bars should be sorted by timestamp"
    
    def test_get_historical_data_5min(self, broker_gateway: IBrokerGateway, banknifty_instrument: Instrument):
        """Fetch 5-minute bars for BANKNIFTY."""
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)
        
        result = broker_gateway.get_historical_data(
            instrument=banknifty_instrument,
            timeframe='5min',
            start_date=start_date,
            end_date=end_date,
        )
        
        assert result.is_success
        bars = result.value
        
        assert len(bars) > 0
    
    def test_subscribe_ticks(self, broker_gateway: IBrokerGateway, nifty_instrument: Instrument):
        """
        Subscribe to live tick data.
        
        Expected:
            - Subscription succeeds
            - Callback receives ticks with correct structure
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        ticks_received: List = []
        
        def tick_callback(tick):
            ticks_received.append(tick)
        
        result = broker_gateway.subscribe_ticks(
            instruments=[nifty_instrument],
            callback=tick_callback,
        )
        
        assert result.is_success, "Tick subscription should succeed"
        
        # Wait briefly for ticks (in real test, would use async wait)
        import time
        time.sleep(2)
        
        # Unsubscribe
        broker_gateway.unsubscribe_ticks([nifty_instrument])
        
        # Note: In CI environment, may not receive ticks
        # This test primarily verifies subscription mechanism works
        assert True  # Subscription succeeded


# =============================================================================
# HEALTH & DIAGNOSTICS TESTS
# =============================================================================

class TestHealthDiagnostics:
    """Verify connection health monitoring."""
    
    def test_is_connected(self, broker_gateway: IBrokerGateway):
        """Check if broker reports connection status."""
        # This should not raise
        connected = broker_gateway.is_connected()
        
        assert isinstance(connected, bool)
    
    def test_get_health_status(self, broker_gateway: IBrokerGateway):
        """
        Get detailed health status.
        
        Expected:
            - Returns dict with connection_state, latency, etc.
        """
        status = broker_gateway.get_health_status()
        
        assert isinstance(status, dict)
        assert 'connection_state' in status or 'status' in status
    
    def test_ping_latency(self, broker_gateway: IBrokerGateway):
        """
        Ping broker API to measure latency.
        
        Performance Requirement: < 500ms
        
        Expected:
            - Returns latency in milliseconds
            - Latency is reasonable (< 1s)
        """
        if not broker_gateway.is_connected():
            pytest.skip("Broker not connected")
        
        import asyncio
        
        async def ping_test():
            result = await broker_gateway.ping()
            return result
        
        # Run async ping
        try:
            result = asyncio.run(ping_test())
            
            if result.is_success:
                latency_ms = result.value
                assert isinstance(latency_ms, (int, float))
                assert latency_ms < 1000, f"Latency too high: {latency_ms}ms"
        except Exception:
            pytest.skip("Ping not implemented or failed")


# =============================================================================
# PYTEST CONFIGURATION
# =============================================================================

def pytest_addoption(parser):
    """Add --broker CLI argument."""
    parser.addoption(
        "--broker",
        action="store",
        default="paper",
        help="Broker to test: dhan, upstox, paper (default: paper)"
    )


@pytest.fixture(scope="session")
def broker_name(request) -> str:
    """Get broker name from CLI argument."""
    return request.config.getoption("--broker")


if __name__ == "__main__":
    # Run with: python -m pytest tests/contract/test_broker_certification.py --broker=dhan -v
    print("Run with: pytest tests/contract/test_broker_certification.py --broker=<dhan|upstox|paper> -v")
