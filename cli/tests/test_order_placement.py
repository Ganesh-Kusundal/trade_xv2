"""Tests for order placement CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cli.commands.order_placement import (
    cancel_order,
    modify_order,
    place_order,
    place_orders_batch,
)
from cli.commands.registry import CommandResult
from domain import OrderStatus


@pytest.fixture()
def mock_broker_service():
    """Mock broker service."""
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
def mock_composer():
    """Mock ExecutionComposer."""
    return MagicMock()


@pytest.fixture()
def mock_place_response():
    """Create a mock OrderResponse for place_order success."""
    resp = MagicMock()
    resp.order_id = "TEST-ORDER-001"
    resp.symbol = "RELIANCE"
    resp.status = OrderStatus.OPEN
    return resp


@pytest.fixture()
def mock_cancel_response():
    """Create a mock OrderResponse for cancel_order success."""
    resp = MagicMock()
    resp.success = True
    resp.order_id = "TEST-ORDER-001"
    resp.error = ""
    return resp


@pytest.fixture()
def mock_modify_response():
    """Create a mock OrderResponse for modify_order success."""
    resp = MagicMock()
    resp.success = True
    resp.order_id = "TEST-ORDER-001"
    resp.error = ""
    return resp


@pytest.fixture()
def mock_csv_file(tmp_path):
    """Create a temporary CSV file with order data."""
    csv_content = """symbol,side,quantity,type,price,exchange,product
RELIANCE,BUY,10,MARKET,0,NSE,INTRADAY
INFY,SELL,20,LIMIT,1500.00,NSE,CNC
TATAMOTORS,BUY,50,MARKET,0,NSE,INTRADAY"""
    csv_file = tmp_path / "orders.csv"
    csv_file.write_text(csv_content)
    return csv_file


class TestPlaceOrder:
    """Test place_order command."""

    def test_place_order_market_success(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test successful market order placement."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["order_id"] == "TEST-ORDER-001"
            assert result.data["symbol"] == "RELIANCE"
            assert result.data["side"] == "BUY"
            assert result.data["quantity"] == 10

    def test_place_order_limit_success(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test successful limit order placement."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10", "--type", "LIMIT", "--price", "2450.00"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_with_exchange(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order with custom exchange."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["NIFTY24600CE", "SELL", "75", "--exchange", "NFO"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_with_product_type(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order with CNC product type."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10", "--product", "CNC"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_missing_arguments(self, mock_broker_service, mock_console):
        """Test order with missing arguments."""
        result = place_order(
            ["RELIANCE"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Missing required arguments" in result.error

    def test_place_order_invalid_side(self, mock_broker_service, mock_console):
        """Test order with invalid side."""
        result = place_order(
            ["RELIANCE", "INVALID", "10"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid side" in result.error

    def test_place_order_invalid_quantity_zero(self, mock_broker_service, mock_console):
        """Test order with zero quantity."""
        result = place_order(
            ["RELIANCE", "BUY", "0"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid quantity" in result.error

    def test_place_order_invalid_quantity_negative(self, mock_broker_service, mock_console):
        """Test order with negative quantity."""
        result = place_order(
            ["RELIANCE", "BUY", "-5"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid quantity" in result.error

    def test_place_order_invalid_quantity_not_number(self, mock_broker_service, mock_console):
        """Test order with non-numeric quantity."""
        result = place_order(
            ["RELIANCE", "BUY", "abc"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid quantity" in result.error

    def test_place_order_invalid_order_type(self, mock_broker_service, mock_console):
        """Test order with invalid order type."""
        result = place_order(
            ["RELIANCE", "BUY", "10", "--type", "INVALID"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid order type" in result.error

    def test_place_order_invalid_price(self, mock_broker_service, mock_console):
        """Test order with invalid price."""
        result = place_order(
            ["RELIANCE", "BUY", "10", "--price", "abc"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid price" in result.error

    def test_place_order_oms_rejected(self, mock_broker_service, mock_console, mock_composer):
        """Test order rejected by OMS."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch(
                "cli.commands.order_placement._run_async",
                side_effect=RuntimeError("Risk check failed"),
            ),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert "Risk check failed" in result.error

    def test_place_order_network_error(self, mock_broker_service, mock_console, mock_composer):
        """Test order with network error."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch(
                "cli.commands.order_placement._run_async",
                side_effect=ConnectionError("Network timeout"),
            ),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert "Network timeout" in result.error

    @pytest.mark.parametrize("side", ["BUY", "SELL", "buy", "sell"])
    def test_place_order_case_insensitive_side(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response, side
    ):
        """Test order with case-insensitive side."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", side, "10"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    @pytest.mark.parametrize("order_type", ["MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"])
    def test_place_order_all_order_types(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response, order_type
    ):
        """Test all order types."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10", "--type", order_type],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    @pytest.mark.parametrize("exchange", ["NSE", "BSE", "NFO", "MCX", "CDS"])
    def test_place_order_all_exchanges(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response, exchange
    ):
        """Test all exchanges."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10", "--exchange", exchange],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    @pytest.mark.parametrize("product", ["INTRADAY", "CNC", "MARGIN"])
    def test_place_order_all_product_types(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response, product
    ):
        """Test all product types."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10", "--product", product],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True


class TestCancelOrder:
    """Test cancel_order command."""

    def test_cancel_order_success(
        self, mock_broker_service, mock_console, mock_composer, mock_cancel_response
    ):
        """Test successful order cancellation."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_cancel_response),
        ):
            result = cancel_order(
                ["TEST-ORDER-001"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["order_id"] == "TEST-ORDER-001"

    def test_cancel_order_failure(self, mock_broker_service, mock_console, mock_composer):
        """Test failed order cancellation."""
        fail_resp = MagicMock()
        fail_resp.success = False
        fail_resp.error = "Order not cancellable"

        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=fail_resp),
        ):
            result = cancel_order(
                ["TEST-ORDER-001"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert "Failed to cancel" in result.error

    def test_cancel_order_missing_order_id(self, mock_broker_service, mock_console):
        """Test cancellation with missing order ID."""
        result = cancel_order(
            [],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Missing order ID" in result.error

    def test_cancel_order_network_error(self, mock_broker_service, mock_console, mock_composer):
        """Test cancellation with network error."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch(
                "cli.commands.order_placement._run_async",
                side_effect=ConnectionError("Timeout"),
            ),
        ):
            result = cancel_order(
                ["TEST-ORDER-001"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert "Timeout" in result.error

    def test_cancel_order_not_found(self, mock_broker_service, mock_console, mock_composer):
        """Test cancellation of non-existent order."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch(
                "cli.commands.order_placement._run_async",
                side_effect=ValueError("Order not found"),
            ),
        ):
            result = cancel_order(
                ["NONEXISTENT"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert "Order not found" in result.error


class TestModifyOrder:
    """Test modify_order command."""

    def test_modify_order_price_only(
        self, mock_broker_service, mock_console, mock_composer, mock_modify_response
    ):
        """Test modifying order price."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_modify_response),
        ):
            result = modify_order(
                ["TEST-ORDER-001", "--price", "2500.00"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["new_price"] == "2500.00"

    def test_modify_order_quantity_only(
        self, mock_broker_service, mock_console, mock_composer, mock_modify_response
    ):
        """Test modifying order quantity."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_modify_response),
        ):
            result = modify_order(
                ["TEST-ORDER-001", "--quantity", "100"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["new_quantity"] == 100

    def test_modify_order_both_price_and_quantity(
        self, mock_broker_service, mock_console, mock_composer, mock_modify_response
    ):
        """Test modifying both price and quantity."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_modify_response),
        ):
            result = modify_order(
                ["TEST-ORDER-001", "--price", "2500.00", "--quantity", "100"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_modify_order_missing_order_id(self, mock_broker_service, mock_console):
        """Test modification with missing order ID."""
        result = modify_order(
            [],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Missing order ID" in result.error

    def test_modify_order_no_modifications(self, mock_broker_service, mock_console):
        """Test modification without --price or --quantity."""
        result = modify_order(
            ["TEST-ORDER-001"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "No modifications specified" in result.error

    def test_modify_order_invalid_price(self, mock_broker_service, mock_console):
        """Test modification with invalid price."""
        result = modify_order(
            ["TEST-ORDER-001", "--price", "abc"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid price" in result.error

    def test_modify_order_invalid_quantity(self, mock_broker_service, mock_console):
        """Test modification with invalid quantity."""
        result = modify_order(
            ["TEST-ORDER-001", "--quantity", "abc"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Invalid quantity" in result.error

    def test_modify_order_failure(self, mock_broker_service, mock_console, mock_composer):
        """Test failed modification."""
        fail_resp = MagicMock()
        fail_resp.success = False
        fail_resp.error = "Order not modifiable"

        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=fail_resp),
        ):
            result = modify_order(
                ["TEST-ORDER-001", "--price", "2500.00"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False
            assert "Failed to modify" in result.error


class TestPlaceOrdersBatch:
    """Test place_orders_batch command."""

    def test_batch_orders_success(
        self, mock_broker_service, mock_console, mock_csv_file, mock_composer, mock_place_response
    ):
        """Test successful batch order placement."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_orders_batch(
                ["--file", str(mock_csv_file)],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
            assert result.data["total"] == 3
            assert result.data["successful"] == 3
            assert result.data["failed"] == 0

    def test_batch_orders_file_not_found(self, mock_broker_service, mock_console):
        """Test batch order with non-existent file."""
        result = place_orders_batch(
            ["--file", "/nonexistent.csv"],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "File not found" in result.error

    def test_batch_orders_missing_file_argument(self, mock_broker_service, mock_console):
        """Test batch order without --file argument."""
        result = place_orders_batch(
            [],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Missing --file argument" in result.error

    def test_batch_orders_empty_csv(self, mock_broker_service, mock_console, tmp_path):
        """Test batch order with empty CSV."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("symbol,side,quantity,type,price,exchange,product\n")

        result = place_orders_batch(
            ["--file", str(csv_file)],
            mock_broker_service,
            mock_console,
        )

        assert result.success is False
        assert "Empty CSV file" in result.error

    def test_batch_orders_partial_failure(
        self, mock_broker_service, mock_console, mock_csv_file, mock_composer, mock_place_response
    ):
        """Test batch order with partial failures."""
        call_count = [0]

        def side_effect_factory(coro):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Risk check failed")
            return mock_place_response

        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", side_effect=side_effect_factory),
        ):
            result = place_orders_batch(
                ["--file", str(mock_csv_file)],
                mock_broker_service,
                mock_console,
            )

            assert result.success is False  # Has failures
            assert result.data["total"] == 3
            assert result.data["successful"] == 2
            assert result.data["failed"] == 1

    def test_batch_orders_csv_read_error(self, mock_broker_service, mock_console, tmp_path):
        """Test batch order with CSV read error."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("invalid,csv\nformat")

        # This should still parse but may have issues
        result = place_orders_batch(
            ["--file", str(csv_file)],
            mock_broker_service,
            mock_console,
        )

        # May succeed or fail depending on data, but shouldn't crash
        assert isinstance(result, CommandResult)


class TestOrderPlacementIntegration:
    """Integration tests for order placement workflow."""

    def test_place_then_cancel_workflow(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response, mock_cancel_response
    ):
        """Test placing an order then cancelling it."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            place_result = place_order(
                ["RELIANCE", "BUY", "10"],
                mock_broker_service,
                mock_console,
            )
            assert place_result.success is True

        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_cancel_response),
        ):
            cancel_result = cancel_order(
                ["TEST-ORDER-001"],
                mock_broker_service,
                mock_console,
            )
            assert cancel_result.success is True

    def test_place_modify_cancel_workflow(
        self, mock_broker_service, mock_console, mock_composer,
        mock_place_response, mock_modify_response, mock_cancel_response
    ):
        """Test complete lifecycle: place, modify, cancel."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            place_result = place_order(
                ["RELIANCE", "BUY", "10", "--type", "LIMIT", "--price", "2450.00"],
                mock_broker_service,
                mock_console,
            )
            assert place_result.success is True

        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_modify_response),
        ):
            modify_result = modify_order(
                ["TEST-ORDER-001", "--price", "2460.00"],
                mock_broker_service,
                mock_console,
            )
            assert modify_result.success is True

        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_cancel_response),
        ):
            cancel_result = cancel_order(
                ["TEST-ORDER-001"],
                mock_broker_service,
                mock_console,
            )
            assert cancel_result.success is True


class TestOrderPlacementEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_place_order_large_quantity(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order with large quantity."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "1000000"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_decimal_price(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order with decimal price."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["RELIANCE", "BUY", "10", "--type", "LIMIT", "--price", "2450.75"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_futures_contract(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order for futures contract."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["NIFTY24JANFUT", "BUY", "50", "--exchange", "NFO"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_options_contract(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order for options contract."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["NIFTY24600CE", "SELL", "75", "--exchange", "NFO"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_commodity(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order for commodity."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["GOLD", "BUY", "1", "--exchange", "MCX"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True

    def test_place_order_currency(
        self, mock_broker_service, mock_console, mock_composer, mock_place_response
    ):
        """Test order for currency pair."""
        with (
            patch("cli.commands.order_placement._get_execution_composer", return_value=mock_composer),
            patch("cli.commands.order_placement._run_async", return_value=mock_place_response),
        ):
            result = place_order(
                ["USDINR", "BUY", "1000", "--exchange", "CDS"],
                mock_broker_service,
                mock_console,
            )

            assert result.success is True
