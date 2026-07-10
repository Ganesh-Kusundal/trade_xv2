"""Tests for order composition CLI commands."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from interface.ui.commands.order_composition import (
    place_basket_order,
    place_bracket_order,
    place_oco_order,
)
from domain import Order, OrderStatus, Side


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
def mock_order():
    """Create a mock Order object."""
    order = MagicMock(spec=Order)
    order.order_id = "TEST-ORDER-001"
    order.symbol = "RELIANCE"
    order.side = Side.BUY
    order.quantity = 10
    order.price = Decimal("2450.50")
    order.order_type = "MARKET"
    order.status = OrderStatus.OPEN
    return order


def _make_order_response(order_id="TEST-ORDER-001", status=OrderStatus.OPEN):
    resp = MagicMock()
    resp.order_id = order_id
    resp.status = status
    return resp


class TestBracketOrder:
    """Test bracket order functionality."""

    def test_bracket_order_success(self, mock_broker_service, mock_console, mock_order):
        """Test successful bracket order placement."""
        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("ENTRY-001"),
                _make_order_response("TARGET-001"),
                _make_order_response("SL-001"),
            ]

            result = place_bracket_order(
                ["RELIANCE", "BUY", "10", "--target", "2500", "--stop-loss", "2400"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["entry_order_id"] == "ENTRY-001"
            assert result.data["target_order_id"] == "TARGET-001"
            assert result.data["stop_loss_order_id"] == "SL-001"
            assert mock_run.call_count == 3

    def test_bracket_order_missing_arguments(self, mock_broker_service, mock_console):
        """Test bracket order with missing arguments."""
        result = place_bracket_order(["RELIANCE"], mock_broker_service, mock_console)
        assert result.success is False
        assert "Missing required arguments" in result.error

    def test_bracket_order_missing_target(self, mock_broker_service, mock_console):
        """Test bracket order without target price."""
        result = place_bracket_order(
            ["RELIANCE", "BUY", "10", "--stop-loss", "2400"],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False
        assert "Missing target" in result.error

    def test_bracket_order_missing_stop_loss(self, mock_broker_service, mock_console):
        """Test bracket order without stop loss."""
        result = place_bracket_order(
            ["RELIANCE", "BUY", "10", "--target", "2500"],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False
        assert "Missing target or stop-loss" in result.error

    def test_bracket_order_invalid_side(self, mock_broker_service, mock_console):
        """Test bracket order with invalid side."""
        result = place_bracket_order(
            ["RELIANCE", "INVALID", "10", "--target", "2500", "--stop-loss", "2400"],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False

    def test_bracket_order_sell(self, mock_broker_service, mock_console, mock_order):
        """Test bracket order for sell side."""
        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("ENTRY-SELL-001"),
                _make_order_response("TARGET-SELL-001"),
                _make_order_response("SL-SELL-001"),
            ]

            result = place_bracket_order(
                ["RELIANCE", "SELL", "10", "--target", "2300", "--stop-loss", "2500"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            place_calls = mock_composer.place_order.call_args_list
            assert place_calls[0][0][0].transaction_type == Side.SELL
            assert place_calls[1][0][0].transaction_type == Side.BUY
            assert place_calls[2][0][0].transaction_type == Side.BUY


class TestOcoOrder:
    """Test OCO (One Cancels Other) order functionality."""

    def test_oco_order_success(self, mock_broker_service, mock_console, mock_order):
        """Test successful OCO order placement."""
        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("OCO-001"),
                _make_order_response("OCO-002"),
            ]

            result = place_oco_order(
                ["RELIANCE", "SELL", "10", "--order1-price", "2500", "--order2-price", "2350"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["order1_id"] == "OCO-001"
            assert result.data["order2_id"] == "OCO-002"
            assert mock_run.call_count == 2

    def test_oco_order_missing_arguments(self, mock_broker_service, mock_console):
        """Test OCO order with missing arguments."""
        result = place_oco_order(["RELIANCE"], mock_broker_service, mock_console)
        assert result.success is False

    def test_oco_order_missing_price1(self, mock_broker_service, mock_console):
        """Test OCO order without first price."""
        result = place_oco_order(
            ["RELIANCE", "SELL", "10", "--order2-price", "2350"],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False

    def test_oco_order_missing_price2(self, mock_broker_service, mock_console):
        """Test OCO order without second price."""
        result = place_oco_order(
            ["RELIANCE", "SELL", "10", "--order1-price", "2500"],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False

    def test_oco_order_buy_side(self, mock_broker_service, mock_console, mock_order):
        """Test OCO order for buy side."""
        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("OCO-BUY-001"),
                _make_order_response("OCO-BUY-002"),
            ]

            result = place_oco_order(
                ["RELIANCE", "BUY", "10", "--order1-price", "2400", "--order2-price", "2350"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True


class TestBasketOrder:
    """Test basket order functionality."""

    def test_basket_order_success(self, mock_broker_service, mock_console, mock_order, tmp_path):
        """Test successful basket order placement."""
        csv_content = """symbol,side,quantity
RELIANCE,BUY,10
INFY,SELL,20
TCS,BUY,15"""
        csv_file = tmp_path / "basket.csv"
        csv_file.write_text(csv_content)

        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("BASKET-001"),
                _make_order_response("BASKET-002"),
                _make_order_response("BASKET-003"),
            ]

            result = place_basket_order(
                ["--file", str(csv_file)],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["total"] == 3
            assert result.data["successful"] == 3
            assert result.data["failed"] == 0
            assert mock_run.call_count == 3

    def test_basket_order_file_not_found(self, mock_broker_service, mock_console):
        """Test basket order with non-existent file."""
        result = place_basket_order(
            ["--file", "/nonexistent.csv"],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False
        assert "File not found" in result.error

    def test_basket_order_missing_file(self, mock_broker_service, mock_console):
        """Test basket order without file argument."""
        result = place_basket_order([], mock_broker_service, mock_console)
        assert result.success is False
        assert "Missing --file argument" in result.error

    def test_basket_order_partial_failure(self, mock_broker_service, mock_console, tmp_path):
        """Test basket order with partial failures."""
        csv_content = """symbol,side,quantity
RELIANCE,BUY,10
INFY,SELL,20
TCS,BUY,15"""
        csv_file = tmp_path / "basket.csv"
        csv_file.write_text(csv_content)

        call_count = [0]

        def mock_await_in_sync_context(coro):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Order rejected")
            return _make_order_response(f"BASKET-{call_count[0]:03d}")

        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context", side_effect=mock_await_in_sync_context):
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer

            result = place_basket_order(
                ["--file", str(csv_file)],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False  # Has failures
            assert result.data["total"] == 3
            assert result.data["successful"] == 2
            assert result.data["failed"] == 1

    def test_basket_order_empty_csv(self, mock_broker_service, mock_console, tmp_path):
        """Test basket order with empty CSV."""
        csv_content = "symbol,side,quantity\n"
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text(csv_content)

        result = place_basket_order(
            ["--file", str(csv_file)],
            mock_broker_service,
            mock_console,
        )
        assert result.success is False
        assert "Empty CSV file" in result.error


class TestCompositionEdgeCases:
    """Test edge cases for order composition."""

    def test_bracket_order_large_quantity(self, mock_broker_service, mock_console, mock_order):
        """Test bracket order with large quantity."""
        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("BIG-001"),
                _make_order_response("BIG-002"),
                _make_order_response("BIG-003"),
            ]

            result = place_bracket_order(
                ["RELIANCE", "BUY", "10000", "--target", "2500", "--stop-loss", "2400"],
                mock_broker_service,
                mock_console,
            )
            assert result.success is True

    def test_oco_order_decimal_prices(self, mock_broker_service, mock_console, mock_order):
        """Test OCO order with decimal prices."""
        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = [
                _make_order_response("DEC-001"),
                _make_order_response("DEC-002"),
            ]

            result = place_oco_order(
                [
                    "RELIANCE",
                    "SELL",
                    "10",
                    "--order1-price",
                    "2500.75",
                    "--order2-price",
                    "2350.25",
                ],
                mock_broker_service,
                mock_console,
            )
            assert result.success is True

    def test_basket_order_invalid_symbol(self, mock_broker_service, mock_console, tmp_path):
        """Test basket order with invalid symbol."""
        csv_content = """symbol,side,quantity
INVALID_SYMBOL,BUY,10"""
        csv_file = tmp_path / "invalid.csv"
        csv_file.write_text(csv_content)

        with patch("interface.ui.commands.order_composition._get_execution_composer") as mock_composer_fn, \
             patch("interface.ui.commands.order_composition._await_in_sync_context") as mock_run:
            mock_composer = MagicMock()
            mock_composer_fn.return_value = mock_composer
            mock_run.side_effect = ValueError("Symbol not found")

            result = place_basket_order(
                ["--file", str(csv_file)],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert result.data["failed"] == 1
