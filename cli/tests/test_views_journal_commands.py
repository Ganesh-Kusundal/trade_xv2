"""Unit tests for views and journal CLI commands.

Tests cover DuckDB view management and trade journal operations.
All database operations are mocked — no live database dependency.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from cli.commands import journal as cmd_journal
from cli.commands import views as cmd_views


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def console():
    """Return a Rich console with recording enabled."""
    return Console(record=True)


# ---------------------------------------------------------------------------
# Test Views Commands
# ---------------------------------------------------------------------------


class TestViewsCreate:
    """Tests for views create command."""

    def test_create_views_success(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.create_all.return_value = {"layer1": 0.5, "layer2": 0.3}
            mock_vm.view_count.return_value = 15
            mock_vm_cls.return_value = mock_vm

            cmd_views._create_views(console)

            output = console.export_text()
            assert "View Creation Timings" in output
            assert "15" in output
            mock_vm.create_all.assert_called_once()

    def test_create_views_failure(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.create_all.side_effect = Exception("DB error")
            mock_vm_cls.return_value = mock_vm

            # Should not raise - ViewManager.close() is in finally block
            cmd_views._create_views(console)


class TestViewsList:
    """Tests for views list command."""

    def test_list_views_success(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.list_views.return_value = [
                {"name": "view_ohlcv"},
                {"name": "view_trades"},
            ]
            mock_vm.view_columns.return_value = ["timestamp", "open", "high"]
            mock_vm_cls.return_value = mock_vm

            cmd_views._list_views(console)

            output = console.export_text()
            assert "DuckDB Views" in output
            assert "view_ohlcv" in output
            assert "view_trades" in output

    def test_list_views_empty(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.list_views.return_value = []
            mock_vm_cls.return_value = mock_vm

            cmd_views._list_views(console)

            output = console.export_text()
            assert "No views" in output


class TestViewsDrop:
    """Tests for views drop command."""

    def test_drop_views_success(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.view_count.return_value = 15
            mock_vm_cls.return_value = mock_vm

            cmd_views._drop_views(console)

            output = console.export_text()
            assert "Dropped" in output
            assert "15" in output
            mock_vm.drop_all.assert_called_once()


class TestViewsRefresh:
    """Tests for views refresh command."""

    def test_refresh_views_success(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.view_count.return_value = 15
            mock_vm_cls.return_value = mock_vm

            cmd_views._refresh_views(console)

            output = console.export_text()
            assert "Refreshed" in output
            mock_vm.refresh.assert_called_once()


class TestViewsCount:
    """Tests for views count command."""

    def test_count_views(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.view_count.return_value = 15
            mock_vm_cls.return_value = mock_vm

            cmd_views._count_views(console)

            output = console.export_text()
            assert "Total views" in output
            assert "15" in output


class TestViewsBenchmark:
    """Tests for views benchmark command."""

    def test_benchmark_views(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            mock_vm = MagicMock()
            mock_vm.benchmark_all.return_value = [
                {"view": "view_ohlcv", "avg_ms": 12.5, "min_ms": 10.0, "max_ms": 15.0},
                {"view": "view_trades", "avg_ms": 8.3, "min_ms": 7.0, "max_ms": 10.0},
            ]
            mock_vm_cls.return_value = mock_vm

            cmd_views._benchmark_views([], console)

            output = console.export_text()
            assert "Query Performance Benchmark" in output
            assert "view_ohlcv" in output


class TestViewsValidate:
    """Tests for views validate command."""

    def test_validate_views_all_pass(self, console):
        with patch("cli.commands.views.ViewManager") as mock_vm_cls:
            with patch("cli.commands.views.PointInTimeValidator") as mock_validator_cls:
                mock_vm = MagicMock()
                mock_vm_cls.return_value = mock_vm

                mock_validator = MagicMock()
                mock_validator.validate_all.return_value = [
                    MagicMock(view_name="view_ohlcv", is_valid=True, issues=[]),
                    MagicMock(view_name="view_trades", is_valid=True, issues=[]),
                ]
                mock_validator.generate_summary.return_value = {"valid": 2, "invalid": 0}
                mock_validator_cls.return_value = mock_validator

                cmd_views._validate_views(console)

                output = console.export_text()
                assert "Point-In-Time Validation" in output
                assert "passed validation" in output


class TestViewsRouter:
    """Tests for views router command."""

    def test_views_no_args(self, console):
        cmd_views.run_views([], console)
        output = console.export_text()
        assert "DuckDB Analytics" in output

    def test_views_unknown_command(self, console):
        cmd_views.run_views(["unknown"], console)
        output = console.export_text()
        assert "Unknown command" in output

    def test_views_create(self, console):
        with patch("cli.commands.views._create_views") as mock_create:
            cmd_views.run_views(["create"], console)
            mock_create.assert_called_once()

    def test_views_drop(self, console):
        with patch("cli.commands.views._drop_views") as mock_drop:
            cmd_views.run_views(["drop"], console)
            mock_drop.assert_called_once()

    def test_views_list(self, console):
        with patch("cli.commands.views._list_views") as mock_list:
            cmd_views.run_views(["list"], console)
            mock_list.assert_called_once()


# ---------------------------------------------------------------------------
# Test Journal Commands
# ---------------------------------------------------------------------------


class TestJournalRecord:
    """Tests for journal record command."""

    def test_record_trade(self, console):
        with patch("cli.commands.journal.Journal") as mock_journal_cls:
            mock_journal = MagicMock()
            mock_journal.record_trade.return_value = "12345"
            mock_journal_cls.return_value = mock_journal

            cmd_journal.run_journal(["record", "RELIANCE", "BUY", "10", "2450.00"], console)

            output = console.export_text()
            mock_journal.record_trade.assert_called_once()


class TestJournalClose:
    """Tests for journal close command."""

    def test_close_trade(self, console):
        with patch("cli.commands.journal.Journal") as mock_journal_cls:
            mock_journal = MagicMock()
            mock_journal_cls.return_value = mock_journal

            cmd_journal.run_journal(["close", "12345", "2500.00"], console)

            mock_journal.close_trade.assert_called_once()


class TestJournalList:
    """Tests for journal list command."""

    def test_list_trades(self, console):
        with patch("cli.commands.journal.Journal") as mock_journal_cls:
            mock_journal = MagicMock()
            mock_journal.list_trades.return_value = [
                {
                    "trade_id": "12345",
                    "symbol": "RELIANCE",
                    "side": "BUY",
                    "status": "OPEN",
                },
            ]
            mock_journal_cls.return_value = mock_journal

            cmd_journal.run_journal(["list"], console)

            output = console.export_text()
            assert "RELIANCE" in output
            mock_journal.list_trades.assert_called_once()


class TestJournalSummary:
    """Tests for journal summary command."""

    def test_journal_summary(self, console):
        with patch("cli.commands.journal.Journal") as mock_journal_cls:
            mock_journal = MagicMock()
            mock_journal.get_summary.return_value = {
                "total_trades": 50,
                "winning_trades": 30,
                "losing_trades": 20,
                "win_rate": 0.60,
                "total_pnl": 15000.00,
            }
            mock_journal_cls.return_value = mock_journal

            cmd_journal.run_journal(["summary"], console)

            output = console.export_text()
            assert "Journal Summary" in output
            mock_journal.get_summary.assert_called_once()


class TestJournalRouter:
    """Tests for journal router command."""

    def test_journal_no_args(self, console):
        cmd_journal.run_journal([], console)
        output = console.export_text()
        assert "Usage" in output

    def test_journal_unknown_subcommand(self, console):
        cmd_journal.run_journal(["unknown"], console)
        output = console.export_text()
        assert "Unknown" in output

    def test_journal_exception_handling(self, console):
        with patch(
            "cli.commands.journal.Journal",
            side_effect=Exception("DB error"),
        ):
            # Should not crash
            cmd_journal.run_journal(["list"], console)
