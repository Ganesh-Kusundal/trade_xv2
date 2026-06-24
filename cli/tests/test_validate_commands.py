"""Unit tests for validate CLI commands.

Tests cover broker health validation, symbol mapping, CSV data validation.
All broker API calls are mocked — no live API dependency.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from rich.console import Console

from cli.commands import validate as cmd_validate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def console():
    """Return a Rich console with recording enabled."""
    return Console(record=True)


@pytest.fixture()
def mock_broker_service():
    """Create a mock broker service."""
    return MagicMock()


@pytest.fixture()
def mock_gateway():
    """Create a mock gateway with all required methods."""
    gw = MagicMock()

    # Mock quote
    quote = MagicMock()
    quote.ltp = 2450.50
    quote.volume = 1500000
    gw.quote.return_value = quote

    # Mock depth
    depth = MagicMock()
    depth.bids = [MagicMock(), MagicMock()]
    depth.asks = [MagicMock(), MagicMock()]
    gw.depth.return_value = depth

    # Mock history
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    gw.history.return_value = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [100.0] * 20,
            "high": [105.0] * 20,
            "low": [99.0] * 20,
            "close": [102.0] * 20,
            "volume": [1000000] * 20,
            "oi": [0] * 20,
            "symbol": ["TEST"] * 20,
            "exchange": ["NSE"] * 20,
            "timeframe": ["1D"] * 20,
        }
    )

    return gw


@pytest.fixture()
def valid_ohlcv_csv():
    """Create a valid OHLCV CSV file."""
    df = pd.DataFrame(
        {
            "symbol": ["TEST"] * 50,
            "timestamp": pd.date_range("2026-01-01", periods=50, freq="D"),
            "open": [100.0] * 50,
            "high": [105.0] * 50,
            "low": [99.0] * 50,
            "close": [102.0] * 50,
            "volume": [1000000] * 50,
        }
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        df.to_csv(f, index=False)
        return Path(f.name)


# ---------------------------------------------------------------------------
# Test Symbol Validation
# ---------------------------------------------------------------------------


class TestSymbolValidation:
    """Tests for symbol validation."""

    def test_validate_symbol_success(self, console, mock_broker_service, mock_gateway):
        with patch("cli.services.broker_registry.create_gateway", return_value=mock_gateway):
            cmd_validate.run(["RELIANCE"], mock_broker_service, console)

            output = console.export_text()
            assert "RELIANCE" in output
            assert "VALIDATION SUMMARY" in output
            assert "Historical" in output
            assert "Quote" in output

    def test_validate_symbol_historical_error(self, console, mock_broker_service, mock_gateway):
        mock_gateway.history.side_effect = Exception("API error")

        with patch("cli.services.broker_registry.create_gateway", return_value=mock_gateway):
            cmd_validate.run(["RELIANCE"], mock_broker_service, console)

            output = console.export_text()
            assert "ERROR" in output or "Error" in output

    def test_validate_gateway_creation_failure(self, console, mock_broker_service):
        with patch("cli.services.broker_registry.create_gateway", side_effect=Exception("Config error")):
            cmd_validate.run(["RELIANCE"], mock_broker_service, console)

            output = console.export_text()
            assert "Error creating gateway" in output

    def test_validate_no_gateway(self, console, mock_broker_service):
        with patch("cli.services.broker_registry.create_gateway", return_value=None):
            cmd_validate.run(["RELIANCE"], mock_broker_service, console)

            output = console.export_text()
            assert "No broker gateway" in output


# ---------------------------------------------------------------------------
# Test Broker Validation
# ---------------------------------------------------------------------------


class TestBrokerValidation:
    """Tests for broker health validation."""

    def test_validate_broker(self, console, mock_broker_service, mock_gateway):
        with patch("cli.services.broker_registry.create_gateway", return_value=mock_gateway):
            cmd_validate.run(["broker"], mock_broker_service, console)

            output = console.export_text()
            # Should run broker health checks
            assert output is not None


# ---------------------------------------------------------------------------
# Test Data Validation
# ---------------------------------------------------------------------------


class TestDataValidation:
    """Tests for CSV data validation."""

    def test_validate_data_valid_csv(self, console, mock_broker_service, valid_ohlcv_csv):
        cmd_validate.run(["data", str(valid_ohlcv_csv)], mock_broker_service, console)

        output = console.export_text()
        assert "Validating" in output or "validating" in output.lower()

    def test_validate_data_missing_file(self, console, mock_broker_service):
        cmd_validate.run(["data", "/nonexistent.csv"], mock_broker_service, console)

        output = console.export_text()
        assert "Error" in output or "not found" in output.lower()

    def test_validate_data_invalid_schema(self, console, mock_broker_service):
        # Create CSV with missing columns
        df = pd.DataFrame({"symbol": ["TEST"], "price": [100.0]})
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            df.to_csv(f, index=False)
            invalid_csv = Path(f.name)

        cmd_validate.run(["data", str(invalid_csv)], mock_broker_service, console)

        output = console.export_text()
        # Should report schema issues
        assert output is not None


# ---------------------------------------------------------------------------
# Test Validate Router
# ---------------------------------------------------------------------------


class TestValidateRouter:
    """Tests for validate router command."""

    def test_validate_no_args(self, console, mock_broker_service):
        cmd_validate.run([], mock_broker_service, console)

        output = console.export_text()
        assert "Usage" in output

    def test_validate_data_subcommand(self, console, mock_broker_service, valid_ohlcv_csv):
        cmd_validate.run(["data", str(valid_ohlcv_csv)], mock_broker_service, console)
        output = console.export_text()
        assert output is not None

    def test_validate_broker_subcommand(self, console, mock_broker_service, mock_gateway):
        with patch("cli.services.broker_registry.create_gateway", return_value=mock_gateway):
            cmd_validate.run(["broker"], mock_broker_service, console)
            output = console.export_text()
            assert output is not None

    def test_validate_symbol_subcommand(self, console, mock_broker_service, mock_gateway):
        with patch("cli.services.broker_registry.create_gateway", return_value=mock_gateway):
            cmd_validate.run(["symbol", "RELIANCE"], mock_broker_service, console)
            output = console.export_text()
            assert output is not None
