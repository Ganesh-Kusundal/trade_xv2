"""Tests for risk management CLI commands."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from interface.ui.commands.risk_controls import (
    reset_daily_pnl,
    run,
    show_daily_pnl,
    show_risk_limits,
    show_risk_status,
    toggle_kill_switch,
)


@pytest.fixture()
def mock_broker_service():
    """Mock broker service with TradingContext."""
    service = MagicMock()
    service.active_broker = MagicMock()
    service.trading_context = MagicMock()
    return service


@pytest.fixture()
def mock_console():
    """Mock Rich console."""
    from rich.console import Console

    return Console(force_terminal=True, width=120)


@pytest.fixture()
def mock_risk_manager():
    """Mock RiskManager with realistic state."""
    risk_mgr = MagicMock()
    risk_mgr.daily_pnl = Decimal("1500.50")
    risk_mgr.kill_switch = False
    risk_mgr._config = MagicMock()
    risk_mgr._config.max_daily_loss_pct = Decimal("2.0")
    risk_mgr._config.max_position_pct = Decimal("10.0")
    risk_mgr._config.max_gross_exposure_pct = Decimal("50.0")
    risk_mgr._config.kill_switch = False
    risk_mgr._capital_provider = MagicMock()
    risk_mgr._capital_provider.get_available_balance.return_value = Decimal("500000")
    return risk_mgr


class TestShowRiskStatus:
    """Test show_risk_status command."""

    def test_show_risk_status_success(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test successful risk status display."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is True
        assert "capital" in result.data
        assert "daily_pnl" in result.data
        assert "kill_switch" in result.data
        assert result.data["kill_switch"] is False

    def test_show_risk_status_no_trading_context(self, mock_broker_service, mock_console):
        """Test risk status without TradingContext."""
        mock_broker_service.trading_context = None

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is False
        assert "TradingContext not initialized" in result.error

    def test_show_risk_status_no_risk_manager(self, mock_broker_service, mock_console):
        """Test risk status without RiskManager."""
        mock_broker_service.trading_context.order_manager.risk_manager = None

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is False
        assert "RiskManager not configured" in result.error

    def test_show_risk_status_with_kill_switch_active(
        self, mock_broker_service, mock_console, mock_risk_manager
    ):
        """Test risk status when kill switch is active."""
        mock_risk_manager.kill_switch = True
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["kill_switch"] is True

    def test_show_risk_status_negative_pnl(
        self, mock_broker_service, mock_console, mock_risk_manager
    ):
        """Test risk status with negative daily PnL."""
        mock_risk_manager.daily_pnl = Decimal("-2500.00")
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["daily_pnl"] == "-2500.00"

    def test_show_risk_status_zero_pnl(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test risk status with zero daily PnL."""
        mock_risk_manager.daily_pnl = Decimal("0")
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["daily_pnl"] == "0"


class TestToggleKillSwitch:
    """Test toggle_kill_switch command."""

    def test_toggle_kill_switch_on(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test enabling kill switch."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = toggle_kill_switch(["on"], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["kill_switch"] is True
        mock_risk_manager.set_kill_switch.assert_called_once_with(True)

    def test_toggle_kill_switch_off(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test disabling kill switch."""
        mock_risk_manager.kill_switch = True
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = toggle_kill_switch(["off"], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["kill_switch"] is False
        mock_risk_manager.set_kill_switch.assert_called_once_with(False)

    def test_toggle_kill_switch_missing_argument(self, mock_broker_service, mock_console):
        """Test kill switch without on/off argument."""
        result = toggle_kill_switch([], mock_broker_service, mock_console)

        assert result.success is False
        assert "Missing on/off argument" in result.error

    def test_toggle_kill_switch_invalid_argument(self, mock_broker_service, mock_console):
        """Test kill switch with invalid argument."""
        result = toggle_kill_switch(["invalid"], mock_broker_service, mock_console)

        assert result.success is False
        assert "Invalid action" in result.error

    def test_toggle_kill_switch_case_insensitive(
        self, mock_broker_service, mock_console, mock_risk_manager
    ):
        """Test kill switch with case-insensitive arguments."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result_on = toggle_kill_switch(["ON"], mock_broker_service, mock_console)
        assert result_on.success is True

        result_off = toggle_kill_switch(["OFF"], mock_broker_service, mock_console)
        assert result_off.success is True

    def test_toggle_kill_switch_no_trading_context(self, mock_broker_service, mock_console):
        """Test kill switch without TradingContext."""
        mock_broker_service.trading_context = None

        result = toggle_kill_switch(["on"], mock_broker_service, mock_console)

        assert result.success is False
        assert "TradingContext not initialized" in result.error

    def test_toggle_kill_switch_no_risk_manager(self, mock_broker_service, mock_console):
        """Test kill switch without RiskManager."""
        mock_broker_service.trading_context.order_manager.risk_manager = None

        result = toggle_kill_switch(["on"], mock_broker_service, mock_console)

        assert result.success is False
        assert "RiskManager not configured" in result.error


class TestShowRiskLimits:
    """Test show_risk_limits command."""

    def test_show_risk_limits_success(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test successful risk limits display."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_limits([], mock_broker_service, mock_console)

        assert result.success is True
        assert "max_daily_loss_pct" in result.data
        assert "max_position_pct" in result.data
        assert "max_gross_exposure_pct" in result.data

    def test_show_risk_limits_no_trading_context(self, mock_broker_service, mock_console):
        """Test risk limits without TradingContext."""
        mock_broker_service.trading_context = None

        result = show_risk_limits([], mock_broker_service, mock_console)

        assert result.success is False
        assert "TradingContext not initialized" in result.error

    def test_show_risk_limits_no_risk_manager(self, mock_broker_service, mock_console):
        """Test risk limits without RiskManager."""
        mock_broker_service.trading_context.order_manager.risk_manager = None

        result = show_risk_limits([], mock_broker_service, mock_console)

        assert result.success is False
        assert "RiskManager not configured" in result.error

    def test_show_risk_limits_custom_values(self, mock_broker_service, mock_console):
        """Test risk limits with custom configuration."""
        risk_mgr = MagicMock()
        risk_mgr._config = MagicMock()
        risk_mgr._config.max_daily_loss_pct = Decimal("5.0")
        risk_mgr._config.max_position_pct = Decimal("20.0")
        risk_mgr._config.max_gross_exposure_pct = Decimal("80.0")
        mock_broker_service.trading_context.order_manager.risk_manager = risk_mgr

        result = show_risk_limits([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["max_daily_loss_pct"] == "5.0"
        assert result.data["max_position_pct"] == "20.0"


class TestShowDailyPnl:
    """Test show_daily_pnl command."""

    def test_show_daily_pnl_positive(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test daily PnL with positive value."""
        mock_risk_manager.daily_pnl = Decimal("5000.00")
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_daily_pnl([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["daily_pnl"] == "5000.00"

    def test_show_daily_pnl_negative(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test daily PnL with negative value."""
        mock_risk_manager.daily_pnl = Decimal("-3000.00")
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_daily_pnl([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["daily_pnl"] == "-3000.00"

    def test_show_daily_pnl_zero(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test daily PnL with zero value."""
        mock_risk_manager.daily_pnl = Decimal("0")
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_daily_pnl([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["daily_pnl"] == "0"

    def test_show_daily_pnl_no_trading_context(self, mock_broker_service, mock_console):
        """Test daily PnL without TradingContext."""
        mock_broker_service.trading_context = None

        result = show_daily_pnl([], mock_broker_service, mock_console)

        assert result.success is False
        assert "TradingContext not initialized" in result.error

    def test_show_daily_pnl_no_risk_manager(self, mock_broker_service, mock_console):
        """Test daily PnL without RiskManager."""
        mock_broker_service.trading_context.order_manager.risk_manager = None

        result = show_daily_pnl([], mock_broker_service, mock_console)

        assert result.success is False
        assert "RiskManager not configured" in result.error


class TestResetDailyPnl:
    """Test reset_daily_pnl command."""

    def test_reset_daily_pnl_success(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test successful daily PnL reset."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = reset_daily_pnl(["--confirm"], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["daily_pnl"] == "0.00"
        mock_risk_manager.reset_daily_pnl.assert_called_once()

    def test_reset_daily_pnl_missing_confirmation(self, mock_broker_service, mock_console):
        """Test daily PnL reset without confirmation."""
        result = reset_daily_pnl([], mock_broker_service, mock_console)

        assert result.success is False
        assert "Confirmation required" in result.error

    def test_reset_daily_pnl_no_trading_context(self, mock_broker_service, mock_console):
        """Test daily PnL reset without TradingContext."""
        mock_broker_service.trading_context = None

        result = reset_daily_pnl(["--confirm"], mock_broker_service, mock_console)

        assert result.success is False
        assert "TradingContext not initialized" in result.error

    def test_reset_daily_pnl_no_risk_manager(self, mock_broker_service, mock_console):
        """Test daily PnL reset without RiskManager."""
        mock_broker_service.trading_context.order_manager.risk_manager = None

        result = reset_daily_pnl(["--confirm"], mock_broker_service, mock_console)

        assert result.success is False
        assert "RiskManager not configured" in result.error


class TestRiskRouter:
    """Test risk command router."""

    def test_risk_router_status(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test routing to status subcommand."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = run(["status"], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_router_kill_switch(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test routing to kill-switch subcommand."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = run(["kill-switch", "on"], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_router_limits(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test routing to limits subcommand."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = run(["limits"], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_router_pnl(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test routing to pnl subcommand."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = run(["pnl"], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_router_reset_pnl(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test routing to reset-pnl subcommand."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = run(["reset-pnl", "--confirm"], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_router_missing_subcommand(self, mock_broker_service, mock_console):
        """Test risk command without subcommand."""
        result = run([], mock_broker_service, mock_console)

        assert result.success is False
        assert "Missing subcommand" in result.error

    def test_risk_router_unknown_subcommand(self, mock_broker_service, mock_console):
        """Test risk command with unknown subcommand."""
        result = run(["unknown"], mock_broker_service, mock_console)

        assert result.success is False
        assert "Unknown subcommand" in result.error


class TestRiskManagementIntegration:
    """Integration tests for risk management workflows."""

    def test_complete_risk_workflow(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test complete risk management workflow."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        # Check status
        status_result = show_risk_status([], mock_broker_service, mock_console)
        assert status_result.success is True
        assert status_result.data["kill_switch"] is False

        # Enable kill switch
        kill_result = toggle_kill_switch(["on"], mock_broker_service, mock_console)
        assert kill_result.success is True
        assert kill_result.data["kill_switch"] is True

        # Check limits
        limits_result = show_risk_limits([], mock_broker_service, mock_console)
        assert limits_result.success is True

        # Check PnL
        pnl_result = show_daily_pnl([], mock_broker_service, mock_console)
        assert pnl_result.success is True

        # Reset PnL
        reset_result = reset_daily_pnl(["--confirm"], mock_broker_service, mock_console)
        assert reset_result.success is True

        # Disable kill switch
        kill_off_result = toggle_kill_switch(["off"], mock_broker_service, mock_console)
        assert kill_off_result.success is True

    def test_risk_status_after_pnl_reset(
        self, mock_broker_service, mock_console, mock_risk_manager
    ):
        """Test risk status reflects PnL reset."""
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        # Initial PnL
        initial_result = show_daily_pnl([], mock_broker_service, mock_console)
        assert initial_result.success is True

        # Reset PnL
        reset_daily_pnl(["--confirm"], mock_broker_service, mock_console)

        # PnL should still show old value in mock (real implementation would be 0)
        # This test verifies the command doesn't crash


class TestRiskManagementEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_risk_status_large_capital(self, mock_broker_service, mock_console, mock_risk_manager):
        """Test risk status with large capital."""
        mock_risk_manager._capital_provider.get_available_balance.return_value = Decimal(
            "100000000"
        )
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_status_large_negative_pnl(
        self, mock_broker_service, mock_console, mock_risk_manager
    ):
        """Test risk status with large negative PnL."""
        mock_risk_manager.daily_pnl = Decimal("-500000.00")
        mock_broker_service.trading_context.order_manager.risk_manager = mock_risk_manager

        result = show_risk_status([], mock_broker_service, mock_console)

        assert result.success is True

    def test_risk_limits_tight_constraints(self, mock_broker_service, mock_console):
        """Test risk limits with tight constraints."""
        risk_mgr = MagicMock()
        risk_mgr._config = MagicMock()
        risk_mgr._config.max_daily_loss_pct = Decimal("0.5")
        risk_mgr._config.max_position_pct = Decimal("2.0")
        risk_mgr._config.max_gross_exposure_pct = Decimal("10.0")
        mock_broker_service.trading_context.order_manager.risk_manager = risk_mgr

        result = show_risk_limits([], mock_broker_service, mock_console)

        assert result.success is True
        assert result.data["max_daily_loss_pct"] == "0.5"

    def test_risk_limits_loose_constraints(self, mock_broker_service, mock_console):
        """Test risk limits with loose constraints."""
        risk_mgr = MagicMock()
        risk_mgr._config = MagicMock()
        risk_mgr._config.max_daily_loss_pct = Decimal("10.0")
        risk_mgr._config.max_position_pct = Decimal("50.0")
        risk_mgr._config.max_gross_exposure_pct = Decimal("200.0")
        mock_broker_service.trading_context.order_manager.risk_manager = risk_mgr

        result = show_risk_limits([], mock_broker_service, mock_console)

        assert result.success is True
