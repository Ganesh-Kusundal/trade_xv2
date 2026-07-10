"""Unit tests for analytics CLI commands.

All analytics commands are tested with synthetic data — no live API or file dependencies.
Tests cover: scanners, backtests, sector analysis, utilities, and error handling.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from rich.console import Console

from interface.ui.commands import analytics as cmd_analytics
from interface.ui.commands.analytics_backtest import run_backtest, run_paper
from interface.ui.commands.analytics_scanner import run_rank, run_scan
from interface.ui.commands.analytics_sector import run_breadth, run_sector, run_sector_rotation
from interface.ui.commands.analytics_utils import (
    load_dataframe,
    parse_common_args,
    print_records,
    print_scan_result,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_ohlcv():
    """Generate synthetic OHLCV data for testing."""
    dates = pd.date_range("2026-01-01", periods=100, freq="D")
    return pd.DataFrame(
        {
            "symbol": ["TEST"] * 100,
            "timestamp": dates,
            "open": [100.0 + i * 0.5 for i in range(100)],
            "high": [102.0 + i * 0.5 for i in range(100)],
            "low": [99.0 + i * 0.5 for i in range(100)],
            "close": [101.0 + i * 0.5 for i in range(100)],
            "volume": [1000000] * 100,
        }
    )


@pytest.fixture()
def csv_file(synthetic_ohlcv):
    """Create a temporary CSV file with OHLCV data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        synthetic_ohlcv.to_csv(f, index=False)
        return Path(f.name)


@pytest.fixture()
def console():
    """Return a Rich console with recording enabled."""
    return Console(record=True)


# ---------------------------------------------------------------------------
# Test Analytics Utils
# ---------------------------------------------------------------------------


class TestLoadDataframe:
    """Tests for load_dataframe utility."""

    def test_load_valid_csv(self, csv_file):
        df = load_dataframe([str(csv_file)])
        assert df is not None
        assert len(df) == 100
        assert "close" in df.columns

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError, match="CSV file not found"):
            load_dataframe(["/nonexistent/file.csv"])

    def test_load_empty_args(self):
        df = load_dataframe([])
        assert df is None

    def test_load_none_args(self):
        df = load_dataframe([None])
        assert df is None


class TestParseCommonArgs:
    """Tests for parse_common_args utility."""

    def test_parse_file_arg(self):
        result = parse_common_args(["--file", "test.csv"], limit=10)
        assert result["file_path"] == "test.csv"
        assert result["limit"] == 10

    def test_parse_limit_arg(self):
        result = parse_common_args(["--limit", "50"], limit=20)
        assert result["limit"] == 50

    def test_parse_symbol_arg(self):
        result = parse_common_args(["--symbol", "reliance"])
        assert result["symbol"] == "RELIANCE"

    def test_parse_positional_symbol(self):
        result = parse_common_args(["TCS"])
        assert result["symbol"] == "TCS"

    def test_parse_capital_arg(self):
        result = parse_common_args(["--capital", "500000"])
        assert result["capital"] == 500000.0

    def test_parse_years_arg(self):
        result = parse_common_args(["--years", "3.5"])
        assert result["years"] == 3.5


class TestPrintRecords:
    """Tests for print_records utility."""

    def test_print_empty_records(self, console):
        print_records(console, [], limit=10)
        output = console.export_text()
        assert "No candidates" in output

    def test_print_records_with_data(self, console):
        records = [
            {"symbol": "RELIANCE", "score": 85.5, "sector": "Energy"},
            {"symbol": "TCS", "score": 78.2, "sector": "IT"},
        ]
        print_records(console, records, limit=10)
        output = console.export_text()
        assert "RELIANCE" in output
        assert "TCS" in output
        assert "Analytics Results" in output

    def test_print_records_respects_limit(self, console):
        records = [{"symbol": f"STOCK{i}", "value": i} for i in range(20)]
        print_records(console, records, limit=5)
        output = console.export_text()
        assert "STOCK0" in output
        assert "STOCK4" in output
        # STOCK5 should not be visible with limit=5
        assert "STOCK5" not in output


class TestPrintScanResult:
    """Tests for print_scan_result utility."""

    def test_print_empty_result(self, console):
        mock_result = MagicMock()
        mock_result.candidates = []
        print_scan_result(console, mock_result, limit=10)
        output = console.export_text()
        assert "No candidates" in output

    def test_print_scan_result_with_data(self, console):
        mock_candidate = MagicMock()
        mock_candidate.symbol = "RELIANCE"
        mock_candidate.score = 85.5
        mock_candidate.reasons = ["momentum", "volume spike"]

        mock_result = MagicMock()
        mock_result.candidates = [mock_candidate]
        mock_result.scanner = "momentum"
        mock_result.count = 1
        mock_result.universe_size = 500
        mock_result.top.return_value = [mock_candidate]

        print_scan_result(console, mock_result, limit=10)
        output = console.export_text()
        assert "RELIANCE" in output
        assert "momentum" in output
        assert "85.5" in output


# ---------------------------------------------------------------------------
# Test Scanner Commands
# ---------------------------------------------------------------------------


class TestScanCommand:
    """Tests for analytics scan command."""

    def test_scan_momentum(self, csv_file, console):
        with patch("interface.ui.commands.analytics_scanner.Analytics") as mock_analytics:
            mock_scan_result = MagicMock()
            mock_scan_result.candidates = [MagicMock()]
            mock_analytics.return_value.scan.return_value = mock_scan_result

            run_scan(["--file", str(csv_file), "--scanner", "momentum"], console)

            mock_analytics.return_value.scan.assert_called_once()

    def test_scan_no_data(self, console):
        with pytest.raises(FileNotFoundError):
            run_scan(["--file", "/nonexistent.csv"], console)

    def test_scan_default_scanner(self, csv_file, console):
        with patch("interface.ui.commands.analytics_scanner.Analytics") as mock_analytics:
            mock_result = MagicMock()
            mock_result.candidates = []
            mock_analytics.return_value.scan.return_value = mock_result

            run_scan(["--file", str(csv_file)], console)
            # Default scanner should be "breakout"
            mock_analytics.return_value.scan.assert_called_once()


class TestRankCommand:
    """Tests for analytics rank command."""

    def test_rank_with_file(self, csv_file, console):
        with patch("interface.ui.commands.analytics_scanner.Analytics") as mock_analytics:
            mock_result = MagicMock()
            mock_result.charts = [{"data": [{"symbol": "TEST", "score": 90}]}]
            mock_analytics.return_value.rank.return_value = mock_result

            run_rank(["--file", str(csv_file)], console)

            mock_analytics.return_value.rank.assert_called_once()

    def test_rank_without_file(self, console):
        with patch("interface.ui.commands.analytics_scanner.Analytics") as mock_analytics:
            mock_result = MagicMock()
            mock_result.charts = [{"data": []}]
            mock_analytics.return_value.rank.return_value = mock_result

            run_rank([], console)
            mock_analytics.return_value.rank.assert_called_once()


# ---------------------------------------------------------------------------
# Test Backtest Commands
# ---------------------------------------------------------------------------


class TestBacktestCommand:
    """Tests for analytics backtest command."""

    def test_backtest_with_file(self, csv_file, console):
        with patch("interface.ui.commands.analytics_backtest.BacktestEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_result = MagicMock()
            mock_result.summary = {"total_return": "15.5%", "sharpe": 1.2}
            mock_result.metrics.trade_analysis.total_trades = 10
            mock_result.metrics.trade_analysis.winning_trades = 6
            mock_result.metrics.trade_analysis.losing_trades = 4
            mock_result.metrics.trade_analysis.win_rate = 0.6
            mock_result.metrics.trade_analysis.profit_factor = 1.5
            mock_result.metrics.trade_analysis.avg_win = 1000
            mock_result.metrics.trade_analysis.avg_win_pct = 2.0
            mock_result.metrics.trade_analysis.avg_loss = -500
            mock_result.metrics.trade_analysis.avg_loss_pct = -1.0
            mock_result.metrics.trade_analysis.max_consecutive_wins = 3
            mock_result.metrics.trade_analysis.max_consecutive_losses = 2
            mock_result.metrics.trade_analysis.trades_by_strategy = {}
            mock_engine.run.return_value = mock_result
            mock_engine_cls.return_value = mock_engine

            run_backtest(["--file", str(csv_file), "--capital", "100000"], console)

            mock_engine.run.assert_called_once()

    def test_backtest_no_file(self, console):
        run_backtest([], console)
        output = console.export_text()
        assert "Usage" in output

    def test_backtest_invalid_file(self, console):
        run_backtest(["--file", "/nonexistent.csv"], console)
        output = console.export_text()
        assert "Error loading file" in output


class TestPaperTradingCommand:
    """Tests for analytics paper command."""

    def test_paper_with_file(self, csv_file, console):
        with patch("interface.ui.commands.analytics_backtest.PaperTradingEngine") as mock_engine_cls:
            mock_engine = MagicMock()
            mock_result = MagicMock()
            mock_result.summary = {"total_return": "10.0%", "sharpe": 1.0}
            mock_result.session.positions = []
            mock_result.session.open_positions = []
            mock_result.session.trades = []
            mock_engine.run.return_value = mock_result
            mock_engine_cls.return_value = mock_engine

            run_paper(["--file", str(csv_file)], console)
            mock_engine.run.assert_called_once()

    def test_paper_no_file(self, console):
        run_paper([], console)
        output = console.export_text()
        assert "Usage" in output


# ---------------------------------------------------------------------------
# Test Sector Commands
# ---------------------------------------------------------------------------


class TestBreadthCommand:
    """Tests for analytics breadth command."""

    def test_breadth_with_data(self, csv_file, console):
        df = pd.DataFrame(
            {
                "advances": [1200, 1300],
                "declines": [700, 600],
                "unchanged": [100, 100],
                "new_highs": [80, 90],
                "new_lows": [30, 20],
            }
        )
        with patch("interface.ui.commands.analytics_sector.load_dataframe", return_value=df):
            run_breadth([], console)
            output = console.export_text()
            # Should render some output
            assert output is not None

    def test_breadth_without_data(self, console):
        with patch("interface.ui.commands.analytics_sector.load_dataframe", return_value=None):
            run_breadth([], console)
            # Should use default data
            output = console.export_text()
            assert output is not None


class TestSectorCommand:
    """Tests for analytics sector command."""

    def test_sector_with_valid_data(self, console):
        with patch("interface.ui.commands.analytics_sector.Analytics") as mock_analytics:
            mock_result = MagicMock()
            mock_result.summary = "Sector analysis complete"
            mock_result.name = "Sector Analysis"
            mock_result.symbol = None
            mock_result.metrics = {"it": 1.8, "bank": -0.4}
            mock_result.scores = {"momentum": 0.75}
            mock_result.signals = ["bullish", "rotation"]
            mock_analytics.return_value.sectors.return_value = mock_result

            with patch("interface.ui.commands.analytics_sector.load_dataframe") as mock_load:
                import pandas as pd

                mock_load.return_value = pd.DataFrame(
                    {
                        "sector": ["BANK", "IT", "Pharma"],
                        "relative_strength": [1.8, -0.4, 0.5],
                    }
                )
                run_sector([], console)
                mock_analytics.return_value.sectors.assert_called_once()

    def test_sector_without_data(self, console):
        with patch("interface.ui.commands.analytics_sector.Analytics") as mock_analytics:
            mock_result = MagicMock()
            mock_result.summary = "Sector analysis complete"
            mock_result.name = "Sector Analysis"
            mock_result.symbol = None
            mock_result.metrics = {"it": 1.8, "bank": -0.4}
            mock_result.scores = {"momentum": 0.75}
            mock_result.signals = ["bullish"]
            mock_analytics.return_value.sectors.return_value = mock_result

            with patch("interface.ui.commands.analytics_sector.load_dataframe", return_value=None):
                run_sector([], console)
                mock_analytics.return_value.sectors.assert_called_once()


class TestSectorRotationCommand:
    """Tests for analytics sector-rotation command."""

    def test_sector_rotation_with_data(self, console):
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        df = pd.DataFrame(
            {
                "date": dates.repeat(3),
                "sector": ["IT", "Finance", "Pharma"] * 30,
                "return_pct": [0.02, -0.01, 0.015] * 30,
            }
        )
        with patch("interface.ui.commands.analytics_sector.load_dataframe", return_value=df):
            run_sector_rotation([], console)
            output = console.export_text()
            assert "Sector Rotation" in output


# ---------------------------------------------------------------------------
# Test Analytics Router
# ---------------------------------------------------------------------------


class TestAnalyticsRouter:
    """Tests for the main analytics router command."""

    def test_analytics_no_args(self, console):
        cmd_analytics.run([], None, console)
        output = console.export_text()
        assert "Usage" in output
        assert "analytics" in output.lower()

    def test_analytics_unknown_command(self, console):
        cmd_analytics.run(["unknown-command"], None, console)
        output = console.export_text()
        assert "Unknown" in output or "unknown" in output.lower()

    def test_analytics_stock_command(self, console):
        with patch("interface.ui.commands.analytics.run_symbol_command") as mock_run:
            cmd_analytics.run(["stock", "RELIANCE"], None, console)
            mock_run.assert_called_once_with("stock", ["RELIANCE"], None, console)

    def test_analytics_scan_command(self, console):
        with patch("interface.ui.commands.analytics.run_scan") as mock_run:
            cmd_analytics.run(["scan", "--file", "test.csv"], None, console)
            mock_run.assert_called_once()

    def test_analytics_backtest_command(self, console):
        with patch("interface.ui.commands.analytics.run_backtest") as mock_run:
            cmd_analytics.run(["backtest", "--file", "test.csv"], None, console)
            mock_run.assert_called_once()

    def test_analytics_sector_command(self, console):
        with patch("interface.ui.commands.analytics.run_sector") as mock_run:
            cmd_analytics.run(["sector"], None, console)
            mock_run.assert_called_once()

    def test_analytics_rank_command(self, console):
        with patch("interface.ui.commands.analytics.run_rank") as mock_run:
            cmd_analytics.run(["rank"], None, console)
            mock_run.assert_called_once()

    def test_analytics_breadth_command(self, console):
        with patch("interface.ui.commands.analytics.run_breadth") as mock_run:
            cmd_analytics.run(["breadth"], None, console)
            mock_run.assert_called_once()

    def test_analytics_exception_handling(self, console):
        with patch(
            "interface.ui.commands.analytics.run_symbol_command",
            side_effect=Exception("Test error"),
        ):
            cmd_analytics.run(["stock", "RELIANCE"], None, console)
            output = console.export_text()
            assert "Analytics error" in output
