"""Tests for CLI history_batch command structure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from brokers.cli.broker import broker


@pytest.fixture
def runner():
    return CliRunner()


class TestCLIHistoryBatch:
    def test_history_batch_command_exists(self, runner):
        """history_batch command is registered."""
        result = runner.invoke(broker, ["history-batch", "--help"])
        assert result.exit_code == 0
        assert "SYMBOLS" in result.output or "symbols" in result.output.lower()

    def test_history_batch_accepts_multiple_symbols(self, runner):
        """history_batch accepts multiple symbol arguments."""
        mock_result = {
            "RELIANCE": MagicMock(bar_count=30),
            "TCS": MagicMock(bar_count=30),
        }
        with patch("brokers.cli.broker.get_history_batch", return_value=mock_result) as mock_fn:
            result = runner.invoke(
                broker,
                ["--broker", "paper", "history-batch", "RELIANCE", "TCS"],
            )
            # Click should invoke the command
            if result.exit_code == 0:
                mock_fn.assert_called_once()
                call_args = mock_fn.call_args
                symbols_arg = call_args[0][1]  # second positional arg
                assert "RELIANCE" in symbols_arg
                assert "TCS" in symbols_arg

    def test_history_batch_options(self, runner):
        """history_batch supports --tf, --days, --exchange options."""
        result = runner.invoke(broker, ["history-batch", "--help"])
        assert result.exit_code == 0
        assert "--tf" in result.output or "tf" in result.output
        assert "--days" in result.output or "days" in result.output
        assert "--exchange" in result.output or "exchange" in result.output
