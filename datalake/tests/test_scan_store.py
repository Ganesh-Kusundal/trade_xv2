"""Tests for scan result persistence."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from datalake.scan_store import (
    ensure_scan_table,
    save_scan_result,
    get_recent_scans,
    get_scan_symbols,
    compare_scans,
)


@dataclass
class _Candidate:
    """Mock candidate for testing."""
    symbol: str
    score: float
    reasons: list[str] | None = None


@pytest.fixture
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a temporary DuckDB connection for testing."""
    db_path = tmp_path / "test_scan.duckdb"
    c = duckdb.connect(str(db_path))
    ensure_scan_table(c)
    yield c
    c.close()


class TestEnsureScanTable:
    def test_creates_table(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_results'"
        ).fetchone()
        assert result is not None

    def test_idempotent(self, conn: duckdb.DuckDBPyConnection) -> None:
        ensure_scan_table(conn)
        ensure_scan_table(conn)
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_results'"
        ).fetchone()
        assert result is not None


class TestSaveScanResult:
    def test_save_single(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0, ["strong_momentum"])]
        scan_id = save_scan_result("momentum", candidates, 500, conn=conn)
        assert scan_id.startswith("scan_")
        assert "momentum" in scan_id

    def test_save_multiple(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [
            _Candidate("RELIANCE", 85.0),
            _Candidate("INFY", 72.0),
            _Candidate("TCS", 68.0),
        ]
        scan_id = save_scan_result("breakout", candidates, 500, conn=conn)
        symbols = get_scan_symbols(scan_id, conn)
        assert len(symbols) == 3

    def test_save_with_metadata(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0)]
        scan_id = save_scan_result(
            "momentum", candidates, 500,
            metadata={"universe": "nifty500"},
            conn=conn,
        )
        assert scan_id is not None

    def test_scan_id_unique(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0)]
        id1 = save_scan_result("momentum", candidates, 500, conn=conn)
        id2 = save_scan_result("momentum", candidates, 500, conn=conn)
        assert id1 != id2


class TestGetRecentScans:
    def test_empty(self, conn: duckdb.DuckDBPyConnection) -> None:
        scans = get_recent_scans(conn=conn)
        assert scans == []

    def test_with_scans(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0)]
        save_scan_result("momentum", candidates, 500, conn=conn)
        save_scan_result("breakout", candidates, 500, conn=conn)
        scans = get_recent_scans(conn=conn)
        assert len(scans) == 2

    def test_filter_by_scanner(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0)]
        save_scan_result("momentum", candidates, 500, conn=conn)
        save_scan_result("breakout", candidates, 500, conn=conn)
        scans = get_recent_scans(scanner="momentum", conn=conn)
        assert len(scans) == 1
        assert scans[0]["scanner"] == "momentum"

    def test_limit(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0)]
        for i in range(5):
            save_scan_result("momentum", candidates, 500, conn=conn)
        scans = get_recent_scans(limit=3, conn=conn)
        assert len(scans) == 3


class TestGetScanSymbols:
    def test_empty(self, conn: duckdb.DuckDBPyConnection) -> None:
        symbols = get_scan_symbols("nonexistent", conn)
        assert symbols == []

    def test_with_symbols(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [
            _Candidate("RELIANCE", 85.0, ["strong_momentum"]),
            _Candidate("INFY", 72.0, ["volume_spike"]),
        ]
        scan_id = save_scan_result("momentum", candidates, 500, conn=conn)
        symbols = get_scan_symbols(scan_id, conn)
        assert len(symbols) == 2
        assert symbols[0]["symbol"] == "RELIANCE"
        assert symbols[0]["score"] == 85.0

    def test_sorted_by_score(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [
            _Candidate("INFY", 72.0),
            _Candidate("RELIANCE", 85.0),
            _Candidate("TCS", 68.0),
        ]
        scan_id = save_scan_result("momentum", candidates, 500, conn=conn)
        symbols = get_scan_symbols(scan_id, conn)
        scores = [s["score"] for s in symbols]
        assert scores == sorted(scores, reverse=True)


class TestCompareScans:
    def test_identical_scans(self, conn: duckdb.DuckDBPyConnection) -> None:
        candidates = [_Candidate("RELIANCE", 85.0), _Candidate("INFY", 72.0)]
        id1 = save_scan_result("momentum", candidates, 500, conn=conn)
        id2 = save_scan_result("momentum", candidates, 500, conn=conn)
        result = compare_scans(id1, id2, conn)
        assert len(result["added"]) == 0
        assert len(result["removed"]) == 0

    def test_added_symbols(self, conn: duckdb.DuckDBPyConnection) -> None:
        id1 = save_scan_result("momentum", [_Candidate("RELIANCE", 85.0)], 500, conn=conn)
        id2 = save_scan_result("momentum", [
            _Candidate("RELIANCE", 85.0),
            _Candidate("INFY", 72.0),
        ], 500, conn=conn)
        result = compare_scans(id1, id2, conn)
        assert "INFY" in result["added"]

    def test_removed_symbols(self, conn: duckdb.DuckDBPyConnection) -> None:
        id1 = save_scan_result("momentum", [
            _Candidate("RELIANCE", 85.0),
            _Candidate("INFY", 72.0),
        ], 500, conn=conn)
        id2 = save_scan_result("momentum", [_Candidate("RELIANCE", 85.0)], 500, conn=conn)
        result = compare_scans(id1, id2, conn)
        assert "INFY" in result["removed"]

    def test_changed_symbols(self, conn: duckdb.DuckDBPyConnection) -> None:
        id1 = save_scan_result("momentum", [_Candidate("RELIANCE", 80.0)], 500, conn=conn)
        id2 = save_scan_result("momentum", [_Candidate("RELIANCE", 90.0)], 500, conn=conn)
        result = compare_scans(id1, id2, conn)
        assert len(result["changed"]) == 1
        assert result["changed"][0]["delta"] == 10.0

    def test_summary(self, conn: duckdb.DuckDBPyConnection) -> None:
        id1 = save_scan_result("momentum", [_Candidate("RELIANCE", 80.0)], 500, conn=conn)
        id2 = save_scan_result("momentum", [
            _Candidate("RELIANCE", 90.0),
            _Candidate("INFY", 72.0),
        ], 500, conn=conn)
        result = compare_scans(id1, id2, conn)
        assert "Added 1" in result["summary"]
        assert "Changed 1" in result["summary"]
