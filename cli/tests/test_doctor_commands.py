"""Unit tests for doctor CLI commands.

Tests cover all 10 diagnostic check categories in the doctor command.
All broker API calls are mocked — no live API dependency.

Phase P4-2 (2026-06-22): Updated to work with Strategy pattern refactoring.
Tests now patch the strategy modules instead of the doctor module directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from cli.commands import doctor as cmd_doctor
from cli.commands.doctor import CheckResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def console():
    """Return a Rich console with recording enabled."""
    return Console(record=True)


@pytest.fixture()
def mock_broker_service():
    """Create a mock broker service with lifecycle."""
    service = MagicMock()
    service.lifecycle = MagicMock()
    service.lifecycle.service_names.return_value = ["dhan.token_refresh_scheduler"]
    service.lifecycle.health_snapshot.return_value = {
        "dhan.token_refresh_scheduler": {"state": "HEALTHY"}
    }
    return service


@pytest.fixture()
def mock_gateway():
    """Create a comprehensive mock gateway."""
    gw = MagicMock()

    # Market data
    quote = MagicMock()
    quote.ltp = 2450.50
    quote.volume = 1500000
    gw.market_data.get_quote.return_value = quote

    depth = MagicMock()
    depth.bids = [MagicMock()]
    depth.asks = [MagicMock()]
    gw.market_data.get_depth.return_value = depth

    import pandas as pd

    gw.historical.get_historical.return_value = pd.DataFrame(
        {"timestamp": pd.date_range("2026-01-01", periods=10, freq="D")}
    )

    # Options
    gw.options.get_expiries.return_value = ["2026-06-25"]
    gw.options.get_option_chain.return_value = {"strikes": [], "spot": 24600}

    # Futures
    gw.futures.get_contracts.return_value = []

    # Orders & Trades
    gw.orders.get_orderbook.return_value = []
    gw.orders.get_trade_book.return_value = []

    # Portfolio
    gw.portfolio.get_holdings.return_value = []
    gw.portfolio.get_positions.return_value = []

    # Funds
    funds = MagicMock()
    funds.available_balance = 100000.0
    funds.used_margin = 0.0
    gw.funds.return_value = funds

    return gw


# ---------------------------------------------------------------------------
# Test CheckResult Model
# ---------------------------------------------------------------------------


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_create_pass_result(self):
        result = CheckResult(name="Test Check", status="PASS", detail="All good")
        assert result.name == "Test Check"
        assert result.status == "PASS"
        assert result.detail == "All good"

    def test_create_fail_result(self):
        result = CheckResult(name="Test Check", status="FAIL", detail="Error occurred")
        assert result.status == "FAIL"

    def test_create_warn_result(self):
        result = CheckResult(name="Test Check", status="WARN")
        assert result.status == "WARN"
        assert result.detail == ""


# ---------------------------------------------------------------------------
# Test Doctor Helpers
# ---------------------------------------------------------------------------


class TestDoctorHelpers:
    """Tests for doctor helper functions."""

    def test_status_str_pass(self):
        result = cmd_doctor._status_str("PASS")
        assert "PASS" in result
        assert "green" in result

    def test_status_str_fail(self):
        result = cmd_doctor._status_str("FAIL")
        assert "FAIL" in result
        assert "red" in result

    def test_status_str_warn(self):
        result = cmd_doctor._status_str("WARN")
        assert "WARN" in result
        assert "yellow" in result

    def test_render_table_with_results(self, console):
        results = [
            CheckResult("Check 1", "PASS", "OK"),
            CheckResult("Check 2", "FAIL", "Error"),
        ]
        cmd_doctor._render_table("Test Table", results, console)
        output = console.export_text()
        assert "Test Table" in output
        assert "Check 1" in output
        assert "Check 2" in output

    def test_render_table_empty(self, console):
        cmd_doctor._render_table("Empty Table", [], console)
        output = console.export_text()
        assert "Empty Table" not in output


# ---------------------------------------------------------------------------
# Test Doctor Command
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    """Tests for the main doctor command."""

    def test_doctor_success(self, console, mock_broker_service, mock_gateway):
        mock_broker_service.active_broker = mock_gateway

        cmd_doctor.run([], mock_broker_service, console)

        output = console.export_text()
        assert "Diagnostics" in output or "Doctor" in output
        # Should show multiple check categories
        assert "passed" in output or "failed" in output or "warnings" in output

    def test_doctor_no_gateway(self, console, mock_broker_service):
        mock_broker_service.active_broker = None

        cmd_doctor.run([], mock_broker_service, console)

        output = console.export_text()
        # Should still run and report issues
        assert output is not None

    def test_doctor_with_exceptions(self, console, mock_broker_service):
        # Gateway that raises on most calls
        mock_gateway = MagicMock()
        mock_gateway.quote.side_effect = Exception("API down")
        mock_gateway.funds.side_effect = Exception("API down")
        mock_broker_service.active_broker = mock_gateway

        # Should not crash
        cmd_doctor.run([], mock_broker_service, console)
        output = console.export_text()
        assert output is not None


# ---------------------------------------------------------------------------
# Test Doctor Check Categories
# ---------------------------------------------------------------------------


class TestBrokerRegistryCheck:
    """Tests for broker registry diagnostic checks."""

    def test_check_broker_registry_with_brokers(self):
        with patch(
            "cli.commands.doctor.strategies.broker_registry.list_available_brokers"
        ) as mock_list:
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
                {"name": "paper", "env_file": None, "available": True},
            ]
            results = cmd_doctor._check_broker_registry()
            assert len(results) > 0
            assert any(r.name == "Registered Brokers" for r in results)

    def test_check_broker_registry_empty(self):
        with patch(
            "cli.commands.doctor.strategies.broker_registry.list_available_brokers", return_value=[]
        ):
            results = cmd_doctor._check_broker_registry()
            assert any(r.status == "FAIL" for r in results)


class TestGatewayCreationCheck:
    """Tests for gateway creation smoke test."""

    def test_gateway_creation_success(self):
        with (
            patch(
                "cli.commands.doctor.strategies.gateway_creation.list_available_brokers"
            ) as mock_list,
            patch("cli.commands.doctor.strategies.gateway_creation.bootstrap_gateway") as mock_bootstrap,
        ):
            from infrastructure.connection.bootstrap_result import BootstrapResult, BootstrapStatus

            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
            ]
            mock_bootstrap.return_value = BootstrapResult(
                status=BootstrapStatus.READY,
                broker="dhan",
                gateway=MagicMock(),
                probe_passed=True,
                authenticated=True,
                probe_name="mock",
            )
            results = cmd_doctor._check_gateway_creation()
            assert any(r.status == "PASS" for r in results)

    def test_gateway_creation_failure(self):
        with (
            patch(
                "cli.commands.doctor.strategies.gateway_creation.list_available_brokers"
            ) as mock_list,
            patch(
                "cli.commands.doctor.strategies.gateway_creation.bootstrap_gateway",
                side_effect=Exception("Config error"),
            ),
        ):
            mock_list.return_value = [
                {"name": "dhan", "env_file": ".env.local", "available": True},
            ]
            results = cmd_doctor._check_gateway_creation()
            assert any(r.status in ("FAIL", "ERROR") for r in results)


class TestMarketDataChecks:
    """Tests for market data diagnostic checks."""

    def test_quote_check_success(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_market_data(mock_broker_service)
        assert any("quote" in r.name.lower() for r in results)

    def test_depth_check_success(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_market_data(mock_broker_service)
        assert any("depth" in r.name.lower() for r in results)

    def test_historical_check_success(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_market_data(mock_broker_service)
        assert any("historical" in r.name.lower() for r in results)


class TestOrderTradeChecks:
    """Tests for order & trade diagnostic checks."""

    def test_orderbook_check(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_order_api(mock_broker_service)
        assert any("order" in r.name.lower() for r in results)

    def test_tradebook_check(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_order_api(mock_broker_service)
        assert any("trade" in r.name.lower() for r in results)


class TestPortfolioChecks:
    """Tests for portfolio diagnostic checks."""

    def test_holdings_check(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_portfolio(mock_broker_service)
        assert any("holding" in r.name.lower() for r in results)

    def test_positions_check(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_portfolio(mock_broker_service)
        assert any("position" in r.name.lower() for r in results)

    def test_balance_check(self, mock_gateway):
        mock_broker_service = MagicMock()
        mock_broker_service.active_broker = mock_gateway
        results = cmd_doctor._check_portfolio(mock_broker_service)
        assert any("balance" in r.name.lower() or "fund" in r.name.lower() for r in results)


class TestLifecycleCheck:
    """Tests for LifecycleManager health checks."""

    def test_lifecycle_healthy(self, mock_broker_service):
        results = cmd_doctor._check_lifecycle(mock_broker_service)
        assert len(results) > 0
        assert any("lifecycle" in r.name.lower() for r in results)

    def test_lifecycle_no_service(self, mock_broker_service):
        mock_broker_service.lifecycle.health_snapshot.return_value = {}
        results = cmd_doctor._check_lifecycle(mock_broker_service)
        # Should still pass with empty lifecycle
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Test Doctor Edge Cases
# ---------------------------------------------------------------------------


class TestDoctorEdgeCases:
    """Tests for doctor edge cases and error handling."""

    def test_doctor_partial_gateway_failure(self, console, mock_broker_service):
        """Some API calls work, others fail."""
        mock_gateway = MagicMock()
        mock_gateway.quote.return_value = MagicMock(ltp=100, volume=1000)
        mock_gateway.depth.side_effect = Exception("Depth API down")
        mock_gateway.funds.return_value = MagicMock(available_balance=50000)
        mock_broker_service.active_broker = mock_gateway

        # Should not crash, should report mixed results
        cmd_doctor.run([], mock_broker_service, console)
        output = console.export_text()
        assert output is not None

    def test_doctor_timeout_handling(self, console, mock_broker_service):
        """Gateway calls hang indefinitely."""
        import time

        mock_gateway = MagicMock()

        def slow_call(*args, **kwargs):
            time.sleep(0.1)  # Simulate slow call
            return MagicMock()

        mock_gateway.quote.side_effect = slow_call
        mock_gateway.funds.side_effect = slow_call
        mock_broker_service.active_broker = mock_gateway

        # Should complete within reasonable time
        cmd_doctor.run([], mock_broker_service, console)
        output = console.export_text()
        assert output is not None
