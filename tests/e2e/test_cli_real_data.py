"""E2E: Real broker data validation tests.

These tests verify CLI commands work with REAL broker data (no mocks).
Skip in CI - run manually with valid credentials in .env.local.

Usage:
    ./venv/bin/python -m pytest tests/e2e/test_cli_real_data.py -v -k real_broker
"""
import pytest
from rich.console import Console


@pytest.mark.real_broker  # Skip in CI, run manually
class TestDhanRealData:
    """Test Dhan broker with real market data."""

    def test_quote_returns_real_data(self):
        """Verify quote command returns real LTP data."""
        from cli.main import main

        console = Console(force_terminal=True)
        # Execute: tradex quote RELIANCE
        result = main(["quote", "RELIANCE", "--json"], console=console)

        # Verify structure
        assert result["success"] is True
        assert "ltp" in result["data"]
        assert result["data"]["ltp"] > 0  # Real price
        assert result["data"]["symbol"] == "RELIANCE"

    def test_depth_returns_real_data(self):
        """Verify depth command returns real order book."""
        from cli.main import main

        console = Console(force_terminal=True)
        result = main(["depth", "RELIANCE", "--json"], console=console)

        assert result["success"] is True
        assert len(result["data"]["bids"]) > 0
        assert len(result["data"]["asks"]) > 0
        assert result["data"]["bids"][0]["price"] > 0

    def test_holdings_returns_real_data(self):
        """Verify holdings command returns real portfolio data."""
        from cli.main import main

        console = Console(force_terminal=True)
        result = main(["holdings", "--json"], console=console)

        assert result["success"] is True
        # May be empty list if no holdings
        assert isinstance(result["data"], list)

    def test_account_balance_returns_real_data(self):
        """Verify account command returns real balance."""
        from cli.main import main

        console = Console(force_terminal=True)
        result = main(["account", "--json"], console=console)

        assert result["success"] is True
        assert result["data"]["available_balance"] > 0
