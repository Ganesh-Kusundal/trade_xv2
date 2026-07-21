"""Unit tests for doctor check strategies.

Tests each CheckStrategy implementation independently with mocked
broker_service.  Covers happy-path, error-handling, and edge cases
for all 10 diagnostic check strategies.

Phase P4-2 (2026-06-22): Strategy pattern TDD tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.commands.doctor.strategies import (
    ActiveBrokerCheck,
    BrokerRegistryCheck,
    GatewayCreationCheck,
    HTTPObservabilityCheck,
    InstrumentCatalogCheck,
    LifecycleCheck,
    MarketDataCheck,
    OMSRiskManagerCheck,
    OrderAPICheck,
    PortfolioCheck,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_broker_service():
    """Create a mock broker service."""
    service = MagicMock()
    service.active_broker_name = "dhan"
    return service


@pytest.fixture()
def mock_gateway():
    """Create a comprehensive mock gateway."""
    gw = MagicMock()
    gw.describe.return_value = {"type": "live", "name": "Dhan", "version": "1.0"}

    # Capabilities
    caps = MagicMock()
    caps.websocket = True
    caps.depth_20 = True
    caps.depth_200 = False
    caps.super_orders = True
    caps.order_types = ["MARKET", "LIMIT", "SL", "SL-M"]
    caps.rate_limit_per_second = 10
    caps.rate_limit_per_minute = 500
    gw.capabilities.return_value = caps

    return gw


# ---------------------------------------------------------------------------
# Test CheckResult
# ---------------------------------------------------------------------------


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_create_with_all_fields(self):
        result = CheckResult(name="Test", status="PASS", detail="All good")
        assert result.name == "Test"
        assert result.status == "PASS"
        assert result.detail == "All good"

    def test_create_with_default_detail(self):
        result = CheckResult(name="Test", status="FAIL")
        assert result.detail == ""

    def test_all_statuses(self):
        for status in ["PASS", "WARN", "FAIL", "INFO", "ERROR"]:
            result = CheckResult(name="Test", status=status)
            assert result.status == status


# ---------------------------------------------------------------------------
# Test CheckStrategy Protocol
# ---------------------------------------------------------------------------


class TestCheckStrategyProtocol:
    """Tests for CheckStrategy protocol conformance."""

    def test_protocol_requires_execute(self):
        """Verify CheckStrategy protocol requires execute method."""

        class ValidStrategy:
            def execute(self, broker_service) -> list[CheckResult]:
                return [CheckResult("Test", "PASS")]

        # Should not raise
        strategy: CheckStrategy = ValidStrategy()
        results = strategy.execute(None)
        assert len(results) == 1

    def test_strategy_returns_list_of_check_results(self):
        class ValidStrategy:
            def execute(self, broker_service) -> list[CheckResult]:
                return [
                    CheckResult("Check1", "PASS", "OK"),
                    CheckResult("Check2", "FAIL", "Error"),
                ]

        strategy: CheckStrategy = ValidStrategy()
        results = strategy.execute(None)
        assert all(isinstance(r, CheckResult) for r in results)


# ---------------------------------------------------------------------------
# Test BrokerRegistryCheck
# ---------------------------------------------------------------------------


class TestBrokerRegistryCheck:
    """Tests for BrokerRegistryCheck strategy."""

    def test_success_with_brokers(self):
        with patch(
            "interface.ui.commands.doctor.strategies.broker_registry.list_available_brokers"
        ) as mock_list:
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
                {"name": "paper", "env_file": None, "available": True},
            ]
            strategy = BrokerRegistryCheck()
            results = strategy.execute(None)

            assert len(results) >= 1
            assert results[0].name == "Registered Brokers"
            assert results[0].status == "PASS"

    def test_empty_registry(self):
        with patch(
            "interface.ui.commands.doctor.strategies.broker_registry.list_available_brokers",
            return_value=[],
        ):
            strategy = BrokerRegistryCheck()
            results = strategy.execute(None)

            assert len(results) == 1
            assert results[0].status == "FAIL"

    def test_paper_broker_info(self):
        with patch(
            "interface.ui.commands.doctor.strategies.broker_registry.list_available_brokers"
        ) as mock_list:
            mock_list.return_value = [
                {"name": "paper", "env_file": None, "available": True},
            ]
            strategy = BrokerRegistryCheck()
            results = strategy.execute(None)

            # Should have INFO status for paper broker
            assert any(r.status == "INFO" for r in results)

    def test_missing_env_file_warns(self):
        with patch(
            "interface.ui.commands.doctor.strategies.broker_registry.list_available_brokers"
        ) as mock_list:
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": False},
            ]
            strategy = BrokerRegistryCheck()
            results = strategy.execute(None)

            assert any(r.status == "WARN" for r in results)


# ---------------------------------------------------------------------------
# Test GatewayCreationCheck
# ---------------------------------------------------------------------------


class TestGatewayCreationCheck:
    """Tests for GatewayCreationCheck strategy."""

    def test_success(self):
        from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus

        with (
            patch(
                "interface.ui.commands.doctor.strategies.gateway_creation.list_available_brokers"
            ) as mock_list,
            patch(
                "interface.ui.commands.doctor.strategies.gateway_creation.bootstrap_gateway"
            ) as mock_boot,
        ):
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
            ]
            mock_boot.return_value = BootstrapResult(
                status=BootstrapStatus.READY,
                broker="dhan",
                gateway=MagicMock(),
                probe_passed=True,
                authenticated=True,
                probe_name="dhan.funds",
            )

            strategy = GatewayCreationCheck()
            results = strategy.execute(None)

            assert any(r.status == "PASS" for r in results)

    def test_failure_raises_exception(self):
        with (
            patch(
                "interface.ui.commands.doctor.strategies.gateway_creation.list_available_brokers"
            ) as mock_list,
            patch(
                "interface.ui.commands.doctor.strategies.gateway_creation.bootstrap_gateway",
                side_effect=Exception("Config error"),
            ),
        ):
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
            ]

            strategy = GatewayCreationCheck()
            results = strategy.execute(None)

            assert any(r.status == "FAIL" for r in results)

    def test_bootstrap_failed(self):
        from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus

        with (
            patch(
                "interface.ui.commands.doctor.strategies.gateway_creation.list_available_brokers"
            ) as mock_list,
            patch(
                "interface.ui.commands.doctor.strategies.gateway_creation.bootstrap_gateway"
            ) as mock_boot,
        ):
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
            ]
            mock_boot.return_value = BootstrapResult(
                status=BootstrapStatus.FAILED,
                broker="dhan",
                error="credential validation failed",
            )

            strategy = GatewayCreationCheck()
            results = strategy.execute(None)

            assert any(r.status == "FAIL" for r in results)

    def test_paper_broker_skipped(self):
        with patch(
            "interface.ui.commands.doctor.strategies.gateway_creation.list_available_brokers"
        ) as mock_list:
            mock_list.return_value = [
                {"name": "paper", "env_file": None, "available": True},
            ]

            strategy = GatewayCreationCheck()
            results = strategy.execute(None)

            assert any(r.status == "INFO" for r in results)


# ---------------------------------------------------------------------------
# Test ActiveBrokerCheck
# ---------------------------------------------------------------------------


class TestActiveBrokerCheck:
    """Tests for ActiveBrokerCheck strategy."""

    def test_success(self, mock_broker_service, mock_gateway):
        mock_broker_service.active_broker = mock_gateway

        strategy = ActiveBrokerCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Active Broker" and r.status == "PASS" for r in results)
        assert any(r.name == "  Capabilities" for r in results)

    def test_no_broker_service(self):
        strategy = ActiveBrokerCheck()
        results = strategy.execute(None)

        assert len(results) == 1
        assert results[0].status == "FAIL"

    def test_exception_handling(self, mock_broker_service):
        mock_broker_service.active_broker_name = "dhan"
        mock_broker_service.active_broker = MagicMock()
        mock_broker_service.active_broker.describe.side_effect = Exception("Connection lost")

        strategy = ActiveBrokerCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.status == "FAIL" for r in results)


# ---------------------------------------------------------------------------
# Test InstrumentCatalogCheck
# ---------------------------------------------------------------------------


class TestInstrumentCatalogCheck:
    """Tests for InstrumentCatalogCheck strategy."""

    def test_search_success(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_broker_service.active_broker.search.return_value = [{"symbol": "RELIANCE"}]

        strategy = InstrumentCatalogCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Instrument Search" and r.status == "PASS" for r in results)

    def test_search_empty(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_broker_service.active_broker.search.return_value = []

        strategy = InstrumentCatalogCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Instrument Search" and r.status == "WARN" for r in results)

    def test_no_broker_service(self):
        strategy = InstrumentCatalogCheck()
        results = strategy.execute(None)

        assert any(r.status == "FAIL" for r in results)


# ---------------------------------------------------------------------------
# Test MarketDataCheck
# ---------------------------------------------------------------------------


class TestMarketDataCheck:
    """Tests for MarketDataCheck strategy."""

    def test_quote_success(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_session = MagicMock()
        quote = MagicMock()
        quote.ltp = 2450.50
        quote.open = 2400.00
        quote.high = 2460.00
        quote.low = 2390.00
        quote.close = 2440.00
        quote.volume = 1500000

        with patch(
            "interface.ui.services.active_session.get_active_session", return_value=mock_session
        ):
            with patch("interface.ui.services.market_access.refresh_quote", return_value=quote):
                strategy = MarketDataCheck(quick_mode=True)
                results = strategy.execute(mock_broker_service)

        assert any(r.name == "Quote" and r.status == "PASS" for r in results)

    def test_quote_ltp_zero(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_session = MagicMock()
        quote = MagicMock()
        quote.ltp = 0

        with patch(
            "interface.ui.services.active_session.get_active_session", return_value=mock_session
        ):
            with patch("interface.ui.services.market_access.refresh_quote", return_value=quote):
                strategy = MarketDataCheck(quick_mode=True)
                results = strategy.execute(mock_broker_service)

        assert any(r.name == "Quote" and r.status == "WARN" for r in results)

    def test_quick_mode_skips_depth(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_session = MagicMock()
        quote = MagicMock()
        quote.ltp = 2450.50

        with patch(
            "interface.ui.services.active_session.get_active_session", return_value=mock_session
        ):
            with patch("interface.ui.services.market_access.refresh_quote", return_value=quote):
                strategy = MarketDataCheck(quick_mode=True)
                results = strategy.execute(mock_broker_service)

        assert any(r.name == "Market Depth" and r.status == "INFO" for r in results)
        assert any(r.name == "Historical Data" and r.status == "INFO" for r in results)

    def test_no_broker_service(self):
        strategy = MarketDataCheck()
        results = strategy.execute(None)

        assert any(r.status == "FAIL" for r in results)


# ---------------------------------------------------------------------------
# Test OrderAPICheck
# ---------------------------------------------------------------------------


class TestOrderAPICheck:
    """Tests for OrderAPICheck strategy."""

    def test_orderbook_success(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_broker_service.active_broker.get_orderbook.return_value = []
        mock_broker_service.active_broker.get_trade_book.return_value = []

        strategy = OrderAPICheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Order Book" and r.status == "PASS" for r in results)
        assert any(r.name == "Trade Book" and r.status == "PASS" for r in results)

    def test_orderbook_failure(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_broker_service.active_broker.get_orderbook.side_effect = Exception("API down")
        mock_broker_service.active_broker.get_trade_book.return_value = []

        strategy = OrderAPICheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Order Book" and r.status == "FAIL" for r in results)

    def test_no_broker_service(self):
        strategy = OrderAPICheck()
        results = strategy.execute(None)

        assert any(r.status == "FAIL" for r in results)


# ---------------------------------------------------------------------------
# Test PortfolioCheck
# ---------------------------------------------------------------------------


class TestPortfolioCheck:
    """Tests for PortfolioCheck strategy."""

    def test_positions_success(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_session = MagicMock()
        mock_acct = MagicMock()
        mock_acct.positions = []
        mock_acct.holdings = []
        funds = MagicMock()
        funds.available_balance = 100000.0
        funds.sod_limit = 50000.0
        mock_acct.funds = funds

        with patch(
            "interface.ui.services.active_session.get_active_session", return_value=mock_session
        ):
            with patch(
                "interface.ui.services.market_access.refresh_account", return_value=mock_acct
            ):
                strategy = PortfolioCheck()
                results = strategy.execute(mock_broker_service)

        assert any(r.name == "Positions" and r.status == "PASS" for r in results)
        assert any(r.name == "Holdings" and r.status == "PASS" for r in results)
        assert any(r.name == "Funds" and r.status == "PASS" for r in results)

    def test_funds_no_available_balance(self, mock_broker_service):
        mock_broker_service.active_broker = MagicMock()
        mock_session = MagicMock()
        mock_acct = MagicMock()
        mock_acct.positions = []
        mock_acct.holdings = []
        funds = MagicMock()
        funds.available_balance = None
        mock_acct.funds = funds

        with patch(
            "interface.ui.services.active_session.get_active_session", return_value=mock_session
        ):
            with patch(
                "interface.ui.services.market_access.refresh_account", return_value=mock_acct
            ):
                strategy = PortfolioCheck()
                results = strategy.execute(mock_broker_service)

        assert any(r.name == "Funds" and r.status == "WARN" for r in results)

    def test_no_broker_service(self):
        strategy = PortfolioCheck()
        results = strategy.execute(None)

        assert any(r.status == "FAIL" for r in results)


# ---------------------------------------------------------------------------
# Test LifecycleCheck
# ---------------------------------------------------------------------------


class TestLifecycleCheck:
    """Tests for LifecycleCheck strategy."""

    def test_all_healthy(self, mock_broker_service):
        mock_broker_service.lifecycle.health_snapshot.return_value = {
            "service1": {"state": "HEALTHY", "detail": "OK"},
            "service2": {"state": "HEALTHY", "metrics": {"count": 5}},
        }

        strategy = LifecycleCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Lifecycle" and r.status == "PASS" for r in results)
        assert len(results) >= 3  # Summary + 2 services

    def test_degraded_service(self, mock_broker_service):
        mock_broker_service.lifecycle.health_snapshot.return_value = {
            "service1": {"state": "HEALTHY"},
            "service2": {"state": "DEGRADED", "detail": "High latency"},
        }

        strategy = LifecycleCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Lifecycle" and r.status == "WARN" for r in results)

    def test_failed_service(self, mock_broker_service):
        mock_broker_service.lifecycle.health_snapshot.return_value = {
            "service1": {"state": "FAILED", "detail": "Connection lost"},
        }

        strategy = LifecycleCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "Lifecycle" and r.status == "FAIL" for r in results)

    def test_empty_lifecycle(self, mock_broker_service):
        mock_broker_service.lifecycle.health_snapshot.return_value = {}

        strategy = LifecycleCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.status == "WARN" for r in results)

    def test_no_broker_service(self):
        strategy = LifecycleCheck()
        results = strategy.execute(None)

        assert any(r.status == "FAIL" for r in results)


# ---------------------------------------------------------------------------
# Test OMSRiskManagerCheck
# ---------------------------------------------------------------------------


class TestOMSRiskManagerCheck:
    """Tests for OMSRiskManagerCheck strategy."""

    def test_success(self, mock_broker_service):
        tc = MagicMock()
        rm = MagicMock()
        rm.snapshot.return_value = {
            "kill_switch": False,
            "daily_pnl": 1500.50,
            "reset_count": 2,
        }
        tc.risk_manager = rm
        mock_broker_service.trading_context = tc

        strategy = OMSRiskManagerCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "OMS RiskManager" and r.status == "PASS" for r in results)

    def test_no_trading_context(self, mock_broker_service):
        mock_broker_service.trading_context = None

        strategy = OMSRiskManagerCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.status == "WARN" for r in results)

    def test_no_broker_service(self):
        strategy = OMSRiskManagerCheck()
        results = strategy.execute(None)

        assert any(r.status == "WARN" for r in results)


# ---------------------------------------------------------------------------
# Test HTTPObservabilityCheck
# ---------------------------------------------------------------------------


class TestHTTPObservabilityCheck:
    """Tests for HTTPObservabilityCheck strategy."""

    def test_healthy_server(self, mock_broker_service):
        server = MagicMock()
        health = MagicMock()
        health.metrics = {"port": 8080}
        health.state.value = "HEALTHY"
        server.health.return_value = health
        mock_broker_service.http_observability = server

        strategy = HTTPObservabilityCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.name == "HTTP Observability" and r.status == "PASS" for r in results)

    def test_no_server(self, mock_broker_service):
        mock_broker_service.http_observability = None

        strategy = HTTPObservabilityCheck()
        results = strategy.execute(mock_broker_service)

        assert any(r.status == "WARN" for r in results)

    def test_no_broker_service(self):
        strategy = HTTPObservabilityCheck()
        results = strategy.execute(None)

        assert any(r.status == "WARN" for r in results)
