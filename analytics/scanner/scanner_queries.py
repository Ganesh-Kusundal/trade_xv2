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
        return [dict(zip(columns, row)) for row in rows]

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
                    try:
                        metrics[key] = Decimal(str(round(float(val), 6)))
                    except Exception:
                        pass

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
# SQL definitions for pre-built scanners
# ---------------------------------------------------------------------------

_MOMENTUM_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        volume,
        rsi_14,
        roc_5,
        sma_20,
        sma_50,
        relative_volume_20,
        CASE
            WHEN close > sma_20 AND sma_20 > sma_50 THEN 'up'
            WHEN close < sma_20 AND sma_20 < sma_50 THEN 'down'
            ELSE 'neutral'
        END as trend,
        close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) as momentum
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.20 * GREATEST(0, LEAST(100, 50.0 + (rsi_14 - 50.0) * 1.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-10, LEAST(10, roc_5)) * 3.0))
        + 0.25 * CASE trend
            WHEN 'up' THEN 75.0
            WHEN 'down' THEN 25.0
            ELSE 50.0
        END
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-1, LEAST(3, relative_volume_20 - 1.0)) * 15.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-5, LEAST(5, COALESCE(momentum, 0))) * 5.0))
    , 2) as score,
    CASE
        WHEN rsi_14 > 70 THEN 'overbought'
        WHEN rsi_14 < 30 THEN 'oversold'
        ELSE 'neutral_rsi'
    END || ', ' ||
    CASE
        WHEN relative_volume_20 > 2.0 THEN 'high_volume'
        WHEN relative_volume_20 > 1.5 THEN 'above_avg_volume'
        ELSE 'normal_volume'
    END as reason,
    rsi_14,
    roc_5,
    COALESCE(momentum, 0) as momentum_5,
    relative_volume_20,
    trend
FROM latest_features
WHERE rsi_14 IS NOT NULL
ORDER BY score DESC
"""

_VOLUME_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        volume,
        rsi_14,
        atr_14,
        relative_volume_20,
        volume_sma_20,
        volume / NULLIF(volume_sma_20, 0) as vol_ratio
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.40 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-1, LEAST(5, relative_volume_20 - 1.0)) * 12.0))
        + 0.25 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-2, LEAST(3, COALESCE(vol_ratio, 1.0) - 1.0)) * 10.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(0, LEAST(10, COALESCE(atr_14, 0))) * 3.0))
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + (COALESCE(rsi_14, 50.0) - 50.0) * 0.5))
    , 2) as score,
    CASE
        WHEN relative_volume_20 > 3.0 THEN 'extreme_volume'
        WHEN relative_volume_20 > 2.0 THEN 'high_volume'
        WHEN relative_volume_20 > 1.5 THEN 'above_avg_volume'
        ELSE 'normal_volume'
    END || ', ' ||
    CASE
        WHEN vol_ratio > 2.0 THEN 'volume_spike'
        ELSE 'normal_volume_trend'
    END as reason,
    relative_volume_20,
    COALESCE(vol_ratio, 1.0) as vol_ratio,
    atr_14,
    rsi_14
FROM latest_features
WHERE relative_volume_20 IS NOT NULL
ORDER BY score DESC
"""

_RS_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        rsi_14,
        roc_5,
        sma_20,
        sma_50,
        atr_14,
        CASE
            WHEN close > sma_20 AND sma_20 > sma_50 THEN 'up'
            WHEN close < sma_20 AND sma_20 < sma_50 THEN 'down'
            ELSE 'neutral'
        END as trend,
        close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY event_time) as momentum
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.15 * GREATEST(0, LEAST(100, 50.0 + (rsi_14 - 50.0) * 1.0))
        + 0.30 * CASE trend
            WHEN 'up' THEN 75.0
            WHEN 'down' THEN 25.0
            ELSE 50.0
        END
        + 0.25 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-10, LEAST(10, roc_5)) * 3.0))
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-5, LEAST(5, COALESCE(momentum, 0))) * 5.0))
        + 0.15 * GREATEST(0, LEAST(100, 50.0 + GREATEST(0, LEAST(10, COALESCE(atr_14, 0))) * 3.0))
    , 2) as score,
    CASE trend
        WHEN 'up' THEN 'uptrend'
        WHEN 'down' THEN 'downtrend'
        ELSE 'neutral_trend'
    END || ', ' ||
    CASE
        WHEN rsi_14 > 60 THEN 'strong_rsi'
        ELSE 'neutral_rsi'
    END as reason,
    rsi_14,
    roc_5,
    COALESCE(momentum, 0) as momentum_5,
    atr_14,
    trend
FROM latest_features
WHERE rsi_14 IS NOT NULL
ORDER BY score DESC
"""

_BREAKOUT_SQL = """
WITH latest_features AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        event_time,
        close,
        volume,
        rsi_14,
        atr_14,
        relative_volume_20,
        sma_20 as bb_mid,
        sma_20 + 2.0 * STDDEV(close) OVER (
            PARTITION BY symbol ORDER BY event_time
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) as bb_upper,
        sma_20 - 2.0 * STDDEV(close) OVER (
            PARTITION BY symbol ORDER BY event_time
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) as bb_lower,
        SUM(volume * close) OVER (
            PARTITION BY symbol, CAST(event_time AS DATE)
            ORDER BY event_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) / NULLIF(SUM(volume) OVER (
            PARTITION BY symbol, CAST(event_time AS DATE)
            ORDER BY event_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 0) as vwap
    FROM intraday_features
    WHERE published_at <= :as_of_time
      AND event_time <= :as_of_time
    ORDER BY symbol, event_time DESC
)
SELECT
    symbol,
    ROUND(
        0.30 * GREATEST(0, LEAST(100, 50.0 + (
            (close - bb_lower) / NULLIF(bb_upper - bb_lower, 0) - 0.5
        ) * 60.0))
        + 0.30 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-1, LEAST(4, relative_volume_20 - 1.0)) * 15.0))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + (COALESCE(rsi_14, 50.0) - 50.0) * 0.8))
        + 0.20 * GREATEST(0, LEAST(100, 50.0 + GREATEST(-5, LEAST(5,
            (close - COALESCE(vwap, close)) / NULLIF(COALESCE(vwap, close), 0) * 100
        )) * 5.0))
    , 2) as score,
    CASE
        WHEN close >= bb_upper THEN 'near_upper_band'
        WHEN close <= bb_lower THEN 'near_lower_band'
        ELSE 'within_bands'
    END || ', ' ||
    CASE
        WHEN relative_volume_20 > 2.0 THEN 'high_volume'
        ELSE 'normal_volume'
    END as reason,
    close,
    bb_upper,
    bb_mid,
    bb_lower,
    (close - bb_lower) / NULLIF(bb_upper - bb_lower, 0) as bb_pct_b,
    relative_volume_20,
    rsi_14,
    vwap
FROM latest_features
WHERE bb_upper IS NOT NULL AND bb_lower IS NOT NULL
ORDER BY score DESC
"""


# ---------------------------------------------------------------------------
# Pre-built scanners
# ---------------------------------------------------------------------------

momentum_scanner = ScannerQuery(
    name="momentum",
    description="Finds stocks with strong momentum (RSI, ROC, trend alignment). "
    "Matches MomentumScanner scoring logic.",
    sql=_MOMENTUM_SQL,
    top_n=20,
    min_score=0.0,
)

volume_scanner = ScannerQuery(
    name="volume_breakout",
    description="Finds stocks with unusual volume activity. "
    "Matches VolumeScanner scoring logic.",
    sql=_VOLUME_SQL,
    top_n=20,
    min_score=0.0,
)

rs_rotation_scanner = ScannerQuery(
    name="rs_rotation",
    description="Finds stocks with strong relative strength vs benchmark. "
    "Matches RSScanner scoring logic.",
    sql=_RS_SQL,
    top_n=20,
    min_score=0.0,
)

breakout_scanner = ScannerQuery(
    name="breakout",
    description="Finds stocks near breakout (Bollinger squeeze, volume, swing levels). "
    "Matches BreakoutScanner scoring logic.",
    sql=_BREAKOUT_SQL,
    top_n=20,
    min_score=0.0,
)

_BUILTIN_SCANNERS: list[ScannerQuery] = [
    momentum_scanner,
    volume_scanner,
    rs_rotation_scanner,
    breakout_scanner,
]

_SCANNER_MAP: dict[str, ScannerQuery] = {s.name: s for s in _BUILTIN_SCANNERS}


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
