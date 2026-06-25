"""E2E: Initialization flow tests.

Verify BrokerService initialization completes without errors.
"""
import pytest
from unittest.mock import patch


class TestInitializationFlow:
    """Test BrokerService initialization flow."""

    def test_dhan_initialization_succeeds(self):
        """Verify Dhan initialization completes successfully."""
        from cli.services.broker_service import BrokerService

        broker_service = BrokerService(load_instruments=True)
        broker_service._ensure_dhan_initialized()

        # Verify gateway created
        assert broker_service._gateway is not None

        # Verify lifecycle started
        assert broker_service._lifecycle.is_running()

        # Verify readiness checks passed
        assert broker_service._readiness_report is not None

        # Cleanup
        broker_service.close()

    def test_readonly_mode_skips_trading_context(self):
        """Verify readonly mode skips TradingContext initialization."""
        from cli.services.broker_service import BrokerService

        broker_service = BrokerService(load_instruments=False, readonly=True)
        broker_service._ensure_dhan_initialized()

        # Gateway should exist
        assert broker_service._gateway is not None

        # TradingContext should NOT exist
        assert broker_service._trading_context is None

        # Cleanup
        broker_service.close()

    def test_failed_readiness_cleans_up(self):
        """Verify failed readiness check cleans up properly (P-1.5 fix)."""
        from cli.services.broker_service import BrokerService
        from brokers.common.services.production_readiness import ProductionReadinessError

        broker_service = BrokerService(load_instruments=True)

        # Monkey-patch checker to fail
        with patch("brokers.common.services.production_readiness.ProductionReadinessChecker.run_or_raise") as mock_check:
            mock_check.side_effect = ProductionReadinessError("Test failure")

            broker_service._ensure_dhan_initialized()

        # Verify cleanup occurred
        assert broker_service._gateway is None
        assert broker_service._lifecycle.is_running() is False  # Stopped

        # Cleanup
        broker_service.close()
