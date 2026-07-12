"""Query-based scanner framework — pure SQL, no Python feature computation.

Scanners are parameterized SQL queries over pre-computed feature tables.
They are:
- Point-in-time safe: all queries take :as_of_time parameter
- Reproducible: the SQL is the definition
- Fast: run directly in DuckDB over optimized Parquet files

Usage:
    from analytics.scanner.scanner_queries import (
        momentum_scanner, volume_scanner, breakout_scanner,
        ScannerQuery, run_scanner
    )

    # Quick single call
    result = run_scanner("momentum", as_of_time="2024-03-15 11:30:00")

    # Or build a custom scanner
    scanner = ScannerQuery(
        name="my_gap_scanner",
        description="Finds gap-up stocks with volume confirmation",
        sql=\"\"\"
            WITH latest AS (
                SELECT symbol, close, open, volume, published_at
                FROM intraday_features
                WHERE published_at <= :as_of_time
                  AND event_time = (
                      SELECT MAX(event_time) FROM intraday_features
                      WHERE published_at <= :as_of_time
                        AND symbol = intraday_features.symbol
                  )
            )
            SELECT symbol, close, open, volume,
                   (close - open) / open * 100 AS gap_pct,
                   volume / AVG(volume) OVER () AS rel_volume
            FROM latest
            WHERE (close - open) / open * 100 > 1.0
            ORDER BY gap_pct DESC
        \"\"\"
    )
    result = scanner.run(conn, as_of_time="2024-03-15 11:30:00")
    print(result.candidates)
"""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import duckdb

from analytics.scanner.models import Candidate, ScanResult

logger = logging.getLogger(__name__)

_LOOKAHEAD_PATTERNS: list[re.Pattern] = [
    re.compile(r"LEAD\s*\(", re.IGNORECASE),
    re.compile(r"UNBOUNDED\s+FOLLOWING", re.IGNORECASE),
    re.compile(r"ROWS\s+BETWEEN.*?FOLLOWING", re.IGNORECASE),
    re.compile(r"RANGE\s+BETWEEN.*?FOLLOWING", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# ScannerQuery
# ---------------------------------------------------------------------------


@dataclass
class ScannerQuery:
    """A parameterized SQL scanner query.

    Attributes:
        name: Unique scanner identifier.
        description: Human-readable description.
        sql: SQL query with :as_of_time placeholder.
             Must return columns: symbol, score, plus optional reason, metrics.
        top_n: Maximum number of candidates to return.
        min_score: Minimum score threshold (0-100).
    """

    name: str
    description: str
    sql: str
    top_n: int = 20
    min_score: float = 0.0

    def run(
        self,
        conn: duckdb.DuckDBPyConnection,
        as_of_time: str,
    ) -> ScanResult:
        """Execute the scanner query and return ranked candidates.

        The SQL must return at minimum: symbol, score
        Optional: reason (VARCHAR), and any additional metric columns.
        """
        result = self._execute(conn, as_of_time)
        candidates = self._rows_to_candidates(result)
        candidates = [c for c in candidates if float(c.score) >= self.min_score]
        candidates = sorted(candidates, key=lambda c: (-float(c.score), c.symbol))[: self.top_n]

        return ScanResult(
            scanner=self.name,
            candidates=candidates,
            universe_size=len(result),
        )

    def _execute(self, conn: duckdb.DuckDBPyConnection, as_of_time: str) -> list[dict]:
        """Execute SQL and return rows as dicts."""
        param_count = self.sql.count(":as_of_time")
        sql = self.sql.replace(":as_of_time", "?")
        rows = conn.execute(sql, [as_of_time] * param_count).fetchall()
        desc = conn.description
        columns = [d[0] for d in desc] if desc else []
        return [dict(zip(columns, row, strict=False)) for row in rows]

    @staticmethod
    def _rows_to_candidates(rows: list[dict]) -> list[Candidate]:
        candidates: list[Candidate] = []
        for row in rows:
            symbol = str(row.get("symbol", "UNKNOWN"))
            raw_score = row.get("score", 50.0)
            if raw_score is None:
                raw_score = 50.0
            score = Decimal(str(round(float(raw_score), 2))).quantize(Decimal("0.01"))

            reasons_raw = row.get("reason") or row.get("signal") or ""
            reasons = [r.strip() for r in str(reasons_raw).split(",") if r.strip()]

            metrics: dict[str, Decimal] = {}
            for key, val in row.items():
                if key in ("symbol", "score", "reason", "signal", "composite_score"):
                    continue
                if val is not None and isinstance(val, (int, float)):
                    with contextlib.suppress(Exception):
                        metrics[key] = Decimal(str(round(float(val), 6)))

            candidate = Candidate(
                symbol=symbol,
                score=score,
                reasons=reasons,
                metrics=metrics,
            )
            candidates.append(candidate)
        return candidates

    def run_with_catalog(self, catalog: Any, as_of_time: str) -> ScanResult:
        """Run scanner using a DataCatalog (which provides a DuckDB connection)."""
        conn = catalog._conn if hasattr(catalog, "_conn") else catalog.conn
        return self.run(conn, as_of_time)

    def validate(self) -> list[str]:
        """Check SQL for look-ahead patterns (LEAD, FOLLOWING).

        Returns list of warning messages. Empty list means no issues.
        """
        warnings: list[str] = []
        for pattern in _LOOKAHEAD_PATTERNS:
            match = pattern.search(self.sql)
            if match:
                col = match.start()
                line_num = self.sql[:col].count("\n") + 1
                warnings.append(
                    f"Line {line_num}: possible look-ahead pattern — "
                    f"{match.group().strip()!r}"
                )
        return warnings

    def explain(self, conn: duckdb.DuckDBPyConnection) -> str:
        """Return the DuckDB query plan for optimization."""
        plan = conn.execute(f"EXPLAIN {self.sql}").fetchall()
        return "\n".join(row[0] for row in plan) if plan else ""


# ---------------------------------------------------------------------------
# Pre-built scanners (imported from _sql_definitions)
# ---------------------------------------------------------------------------

from analytics.scanner._sql_definitions import (  # noqa: E402
    _BUILTIN_SCANNERS,
    _SCANNER_MAP,
    breakout_scanner,
    momentum_scanner,
    rs_rotation_scanner,
    volume_scanner,
)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def list_scanners() -> list[ScannerQuery]:
    """Return all built-in scanner definitions."""
    return list(_BUILTIN_SCANNERS)


def run_scanner(
    name: str,
    as_of_time: str,
    top_n: int = 10,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> ScanResult:
    """Run a built-in scanner by name.

    Parameters
    ----------
    name: Scanner name (e.g. 'momentum', 'volume_breakout').
    as_of_time: Point-in-time timestamp for PIT-safe queries.
    top_n: Maximum number of candidates.
    conn: DuckDB connection. If None, creates a fresh in-memory one.

    Returns
    -------
    ScanResult with ranked candidates.
    """
    scanner = _SCANNER_MAP.get(name)
    if scanner is None:
        raise ValueError(
            f"Unknown scanner {name!r}. Available: {list(_SCANNER_MAP.keys())}"
        )

    if conn is None:
        conn = duckdb.connect(":memory:")
        should_close = True
    else:
        should_close = False

    try:
        result = scanner.run(conn, as_of_time)
        result.candidates = result.candidates[:top_n]
        return result
    finally:
        if should_close:
            conn.close()


def compare_scanners(
    scanner_names: list[str],
    as_of_time: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, ScanResult]:
    """Run multiple scanners and return all results for comparison.

    Returns dict of scanner_name -> ScanResult.
    """
    if conn is None:
        conn = duckdb.connect(":memory:")
        should_close = True
    else:
        should_close = False

    try:
        results: dict[str, ScanResult] = {}
        for name in scanner_names:
            scanner = _SCANNER_MAP.get(name)
            if scanner is None:
                logger.warning("Unknown scanner %r, skipping", name)
                continue
            results[name] = scanner.run(conn, as_of_time)
        return results
    finally:
        if should_close:
            conn.close()


__all__ = [
    "ScannerQuery",
    "breakout_scanner",
    "compare_scanners",
    "list_scanners",
    "momentum_scanner",
    "rs_rotation_scanner",
    "run_scanner",
    "volume_scanner",
]
