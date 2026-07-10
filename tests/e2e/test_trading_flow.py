"""E2E: Complete trading flow verification.

Verify complete trading flow from CLI to broker to data return.
"""
import pytest


@pytest.mark.real_broker
class TestTradingFlow:
    """Test complete end-to-end trading flows."""

    def test_complete_quote_flow(self):
        """Verify: CLI → BrokerService → Gateway → Dhan API → Quote → CLI"""
        from interface.ui.services.broker_service import BrokerService

        # 1. Initialize broker service
        broker_service = BrokerService(load_instruments=True)
        broker_service._ensure_dhan_initialized()

        # 2. Get gateway
        gw = broker_service.active_broker
        assert gw is not None

        # 3. Call quote (real API)
        quote = gw.quote("RELIANCE", "NSE")

        # 4. Verify quote is real data (not mocked)
        assert quote is not None
        assert quote.ltp > 0
        assert quote.symbol == "RELIANCE"
        assert quote.volume > 0
        assert quote.timestamp is not None

        # 5. Cleanup
        broker_service.close()

    def test_order_placement_flow(self):
        """Verify: CLI → OMS → Risk Check → Gateway → Dhan API → Order ID

        WARNING: This test should be run in sandbox/paper mode only!
        Set TRADING_MODE=paper in .env.local before running.
        """
        from interface.ui.services.broker_service import BrokerService
        from domain import OrderRequest

        broker_service = BrokerService(load_instruments=True)
        broker_service._ensure_dhan_initialized()

        # Place paper order
        oms = broker_service.oms_proxy
        order_id = oms.place_order(OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            order_type="MARKET"
        ))

        assert order_id is not None
        assert len(order_id) > 0

        # Cleanup
        broker_service.close()
