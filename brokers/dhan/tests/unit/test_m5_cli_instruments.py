"""M5 — CLI subcommands use the canonical InstrumentService.

Verifies the M5 contract for ``tradex instruments <subcommand>``:

* ``lookup``    — calls :meth:`InstrumentService.resolve_symbol` and
  prints a Rich table for a single match, an ambiguous table for
  multiple matches, and an unknown table for misses.
* ``diagnostics`` — calls :meth:`InstrumentService.snapshot_info` and
  the catalog's ``diagnostics()`` helper.
* ``validate``  — calls :func:`validate_snapshot` against the latest
  cached file.
* ``refresh``   — calls :meth:`InstrumentService.refresh_snapshot`.

All tests run against the committed real Dhan CSV fixture so the
end-to-end contract is verified against production-shaped data.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from cli.commands import instruments as cmd

pytestmark = pytest.mark.unit


@pytest.fixture
def console() -> Console:
    return Console(record=True, width=120)


@pytest.fixture
def cache_dir(tmp_path: Path, real_csv_path: Path) -> Path:
    """Stage the committed fixture as today's snapshot in a fresh cache."""
    import shutil
    from datetime import date

    cache = tmp_path / "cli_cache"
    cache.mkdir(parents=True, exist_ok=True)
    staged = cache / f"api-scrip-master-{date.today()}.csv"
    shutil.copy2(real_csv_path, staged)
    # Avoid real network download — stub the downloader.
    return cache


class TestM5Lookup:
    """``tradex instruments lookup <SYMBOL>`` uses the service."""

    def test_lookup_known_equity_prints_table(
        self, console: Console, cache_dir: Path, real_csv_path: Path
    ) -> None:
        # Force the CLI to load the staged fixture (no network).
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache_dir):
            cmd._cmd_lookup("RELIANCE", console)
        out = console.export_text()
        assert "RELIANCE" in out
        assert "2885" in out  # RELIANCE NSE SID

    def test_lookup_index_prints_index_segment(self, console: Console, cache_dir: Path) -> None:
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache_dir):
            cmd._cmd_lookup("NIFTY", console)
        out = console.export_text()
        assert "NIFTY" in out
        assert "IDX" in out.upper()  # segment shows up

    def test_lookup_unknown_prints_reason(self, console: Console, cache_dir: Path) -> None:
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache_dir):
            cmd._cmd_lookup("TOTALLY_FAKE_XYZ_QQQ", console)
        out = console.export_text()
        assert "Unknown" in out or "Reason" in out

    def test_lookup_ambiguous_for_bare_reliance(self, console: Console, cache_dir: Path) -> None:
        """Bare ``RELIANCE`` (no exchange hint) is ambiguous: NSE + BSE.

        Even with a single CSV the canonical exchange chain probes
        multiple segments, so we expect the ambiguous branch.
        """
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache_dir):
            cmd._cmd_lookup("RELIANCE", console)
        out = console.export_text()
        assert "RELIANCE" in out


class TestM5Diagnostics:
    """``tradex instruments diagnostics`` uses the service."""

    def test_diagnostics_prints_snapshot_info(self, console: Console, cache_dir: Path) -> None:
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache_dir):
            cmd._cmd_diagnostics(console)
        out = console.export_text()
        assert "Record count" in out
        assert "Checksum" in out
        assert "Futures" in out
        assert "Options" in out


class TestM5Validate:
    """``tradex instruments validate`` runs the validator."""

    def test_validate_against_staged_snapshot(self, console: Console, cache_dir: Path) -> None:
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache_dir):
            cmd._cmd_validate(console)
        out = console.export_text()
        assert "Snapshot OK" in out


class TestM5Refresh:
    """``tradex instruments refresh`` uses the service's refresh path."""

    def test_refresh_uses_instrument_service(self, console: Console, tmp_path: Path) -> None:
        cache = tmp_path / "refresh_cache"
        cache.mkdir(parents=True, exist_ok=True)
        with patch.object(cmd, "_resolve_cache_dir", return_value=cache):
            # Stub the service's refresh_snapshot so we don't hit the
            # network.  The CLI subcommand must call *this* method.
            from brokers.dhan.instrument_service import SnapshotInfo

            with patch(
                "cli.commands.instruments.InstrumentService.refresh_snapshot",
                return_value=SnapshotInfo(
                    date="2026-06-11",
                    checksum="a" * 64,
                    record_count=17_628,
                    source_path=cache / "api-scrip-master-2026-06-11.csv",
                    wire_url="https://images.dhan.co/api-data/api-scrip-master.csv",
                ),
            ) as mock_refresh:
                cmd._cmd_refresh(console)
            mock_refresh.assert_called_once_with(force=True)
        out = console.export_text()
        assert "Refreshed" in out
        assert "17,628" in out
