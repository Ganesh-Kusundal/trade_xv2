"""Data Quality Monitor — automated checks for freshness, completeness, and integrity.

Usage:
    from datalake.quality.monitor import DataQualityMonitor

    monitor = DataQualityMonitor(root="market_data")
    report = monitor.run_checks(timeframe="1m")
    monitor.print_summary(report)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb

from datalake.core.paths import timeframe_partition_dir

logger = logging.getLogger(__name__)


@dataclass
class QualityMetric:
    """Single quality metric."""

    name: str
    value: float
    threshold: float
    status: str  # "PASS", "WARNING", "FAIL"
    details: str = ""


@dataclass
class SymbolQuality:
    """Quality report for a single symbol."""

    symbol: str
    metrics: list[QualityMetric] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Overall status based on worst metric."""
        statuses = [m.status for m in self.metrics]
        if "FAIL" in statuses:
            return "FAIL"
        if "WARNING" in statuses:
            return "WARNING"
        return "PASS"


@dataclass
class OverallReport:
    """Overall quality report."""

    total_symbols: int = 0
    total_candles: int = 0
    date_range: tuple[date | None, date | None] = (None, None)
    symbol_reports: list[SymbolQuality] = field(default_factory=list)
    summary_metrics: list[QualityMetric] = field(default_factory=list)

    @property
    def health_score(self) -> float:
        """Calculate overall health score (0-100)."""
        if not self.symbol_reports:
            return 0.0

        scores = []
        for sr in self.symbol_reports:
            if sr.status == "PASS":
                scores.append(100)
            elif sr.status == "WARNING":
                scores.append(70)
            else:
                scores.append(0)

        return sum(scores) / len(scores) if scores else 0.0


def _expected_candles_per_day(timeframe: str) -> int | None:
    """Return expected candles per trading day for *timeframe*, or None."""
    if timeframe in ("1m", "5m", "15m", "30m"):
        from datalake.core.nse_calendar import expected_candles_per_day

        return expected_candles_per_day(timeframe)
    return None


def _check_freshness(days_old: int, last_date: str) -> tuple[QualityMetric, str | None]:
    metric = QualityMetric(
        name="freshness",
        value=days_old,
        threshold=7.0,
        status="PASS" if days_old <= 1 else "WARNING" if days_old <= 7 else "FAIL",
        details=f"Last update: {last_date} ({days_old} days ago)",
    )
    issue = f"Data is {days_old} days old" if metric.status != "PASS" else None
    return metric, issue


def _check_completeness(
    avg_candles: float, expected: int
) -> tuple[QualityMetric, str | None] | None:
    from datalake.core.nse_calendar import COMPLETENESS_OK_FRACTION

    if expected <= 0:
        return None
    ok_pct = COMPLETENESS_OK_FRACTION * 100
    completeness = min(avg_candles / expected, 1.0)
    pct = completeness * 100
    status = "PASS" if pct >= ok_pct else "WARNING" if pct >= 70 else "FAIL"
    metric = QualityMetric(
        name="completeness",
        value=pct,
        threshold=ok_pct,
        status=status,
        details=f"{avg_candles:.0f}/{expected} candles/day ({pct:.1f}%)",
    )
    issue = f"Only {pct:.0f}% complete ({avg_candles:.0f}/{expected} candles/day)" if status != "PASS" else None
    return metric, issue


def _check_zero_volume(
    zero_vol: int, total: int
) -> tuple[QualityMetric, str | None]:
    pct = (zero_vol / total * 100) if total > 0 else 0.0
    status = "PASS" if pct < 1 else "WARNING" if pct < 10 else "FAIL"
    metric = QualityMetric(
        name="zero_volume",
        value=pct,
        threshold=10.0,
        status=status,
        details=f"{zero_vol:,}/{total:,} ({pct:.1f}%)",
    )
    issue = f"{pct:.1f}% zero volume bars" if status != "PASS" else None
    return metric, issue


def _check_ohlc_integrity(
    ohlc_err: int, total: int
) -> tuple[QualityMetric, str | None]:
    if ohlc_err == 0:
        return QualityMetric(name="ohlc_integrity", value=0, threshold=0, status="PASS", details="No errors"), None
    error_pct = ohlc_err / total * 100
    return (
        QualityMetric(
            name="ohlc_integrity",
            value=error_pct,
            threshold=0,
            status="FAIL",
            details=f"{ohlc_err} errors ({error_pct:.2f}%)",
        ),
        f"{ohlc_err} OHLC errors",
    )


def _evaluate_symbol(sr: dict, expected_per_day: int | None) -> SymbolQuality:
    """Build a SymbolQuality report from a single symbol row."""
    sq = SymbolQuality(symbol=sr["symbol"])

    metric, issue = _check_freshness(int(sr["days_old"]), sr["last_date"])
    sq.metrics.append(metric)
    if issue:
        sq.issues.append(issue)

    if expected_per_day is not None:
        result = _check_completeness(float(sr["avg_candles_per_day"]), expected_per_day)
        if result is not None:
            metric, issue = result
            sq.metrics.append(metric)
            if issue:
                sq.issues.append(issue)

    total = int(sr["total_candles"])
    metric, issue = _check_zero_volume(int(sr["zero_volume"]), total)
    sq.metrics.append(metric)
    if issue:
        sq.issues.append(issue)

    metric, issue = _check_ohlc_integrity(int(sr["ohlc_errors"]), total)
    sq.metrics.append(metric)
    if issue:
        sq.issues.append(issue)

    return sq


class DataQualityMonitor:
    """Automated data quality monitoring."""

    def __init__(
        self,
        root: str | None = None,
        connect_fn: Callable[[], duckdb.DuckDBPyConnection] | None = None,
    ) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS
            root = DEFAULT_DATA_PATHS.lake_root
        self._root = Path(root)
        self._catalog_path = self._root / "catalog.duckdb"
        self._connect = connect_fn or (lambda: duckdb.connect(str(self._catalog_path), read_only=True))

    def run_checks(self, timeframe: str = "1m") -> OverallReport:
        """Run all quality checks with a single-pass DuckDB query.

        Consolidates basic stats, freshness, completeness, and integrity
        checks into one SQL statement to minimise parquet I/O.
        """
        report = OverallReport()

        # Get parquet pattern
        parquet_dir = timeframe_partition_dir(str(self._root), timeframe)
        if not parquet_dir.exists():
            logger.error("Parquet directory not found: %s", parquet_dir)
            return report

        parquet_pattern = str(parquet_dir / "symbol=*" / "data.parquet")

        # Connect to DuckDB
        conn = self._connect()

        try:
            report = self._run_all_checks(conn, parquet_pattern, timeframe, report)
            report = self._calculate_summary(report)
        finally:
            conn.close()

        return report

    # ------------------------------------------------------------------
    # Single consolidated query replacing the former 4 separate scans:
    #   _check_basic_stats  – global symbol/candle counts & date range
    #   _check_freshness    – per-symbol latest timestamp & staleness
    #   _check_completeness – per-symbol avg daily candle count
    #   _check_integrity    – per-symbol zero-volume & OHLC error counts
    #
    # The CTE *daily_counts* requires a second read_parquet call, but
    # DuckDB only reads the columns each scan needs (columnar pruning),
    # so total I/O ≈ 2 full scans vs. the original 4.
    # ------------------------------------------------------------------
    _SINGLE_QUERY = """
        WITH daily_counts AS (
            SELECT
                symbol,
                DATE_TRUNC('day', CAST(timestamp AS TIMESTAMP)) AS day,
                COUNT(*) AS daily_count
            FROM read_parquet(?)
            GROUP BY symbol, DATE_TRUNC('day', CAST(timestamp AS TIMESTAMP))
        ),
        per_symbol AS (
            SELECT
                b.symbol,
                MAX(b.timestamp)::DATE                                   AS last_date,
                DATEDIFF('day', MAX(b.timestamp)::DATE, CURRENT_DATE)     AS days_old,
                COUNT(*)                                                  AS total_candles,
                SUM(CASE WHEN b.volume = 0  THEN 1 ELSE 0 END)           AS zero_volume,
                SUM(CASE WHEN b.high < b.low THEN 1 ELSE 0 END)          AS ohlc_errors,
                COALESCE(MAX(d.trading_days), 0)                          AS trading_days,
                COALESCE(MAX(d.avg_candles_per_day), 0)                   AS avg_candles_per_day
            FROM read_parquet(?) b
            LEFT JOIN (
                SELECT
                    symbol,
                    COUNT(*)             AS trading_days,
                    AVG(daily_count)     AS avg_candles_per_day
                FROM daily_counts
                GROUP BY symbol
            ) d ON b.symbol = d.symbol
            GROUP BY b.symbol
        )
        SELECT
            COUNT(DISTINCT symbol)                                          AS total_symbols,
            SUM(total_candles)                                              AS total_candles,
            MIN(last_date)                                                  AS min_date,
            MAX(last_date)                                                  AS max_date,
            ARRAY_AGG({
                'symbol':              symbol,
                'last_date':           last_date,
                'days_old':            days_old,
                'total_candles':       total_candles,
                'zero_volume':         zero_volume,
                'ohlc_errors':         ohlc_errors,
                'trading_days':        trading_days,
                'avg_candles_per_day': avg_candles_per_day
            })                                                              AS symbol_rows
        FROM per_symbol
    """

    def _run_all_checks(
        self,
        conn: duckdb.DuckDBPyConnection,
        pattern: str,
        timeframe: str,
        report: OverallReport,
    ) -> OverallReport:
        """Execute the consolidated quality query and populate *report*."""
        row = conn.execute(self._SINGLE_QUERY, [pattern, pattern]).fetchone()
        if row is None or not row[1]:  # total_candles is 0 or NULL → empty dataset
            return report

        total_symbols, total_candles, min_date, max_date, symbol_rows = row
        report.total_symbols = total_symbols
        report.total_candles = total_candles
        report.date_range = (min_date, max_date)

        expected_per_day = _expected_candles_per_day(timeframe)

        for sr in symbol_rows:
            sq = _evaluate_symbol(sr, expected_per_day)
            report.symbol_reports.append(sq)

        return report

    def _calculate_summary(self, report: OverallReport) -> OverallReport:
        """Calculate summary metrics."""
        if not report.symbol_reports:
            return report

        # Count statuses
        pass_count = sum(1 for s in report.symbol_reports if s.status == "PASS")
        warn_count = sum(1 for s in report.symbol_reports if s.status == "WARNING")
        fail_count = sum(1 for s in report.symbol_reports if s.status == "FAIL")

        report.summary_metrics = [
            QualityMetric(
                name="symbols_pass",
                value=pass_count,
                threshold=report.total_symbols * 0.8,
                status="PASS" if pass_count >= report.total_symbols * 0.8 else "FAIL",
                details=f"{pass_count}/{report.total_symbols} symbols",
            ),
            QualityMetric(
                name="symbols_warning",
                value=warn_count,
                threshold=report.total_symbols * 0.15,
                status="WARNING" if warn_count <= report.total_symbols * 0.15 else "FAIL",
                details=f"{warn_count}/{report.total_symbols} symbols",
            ),
            QualityMetric(
                name="symbols_fail",
                value=fail_count,
                threshold=report.total_symbols * 0.05,
                status="PASS" if fail_count <= report.total_symbols * 0.05 else "FAIL",
                details=f"{fail_count}/{report.total_symbols} symbols",
            ),
            QualityMetric(
                name="health_score",
                value=report.health_score,
                threshold=80.0,
                status="PASS" if report.health_score >= 80 else "FAIL",
                details=f"{report.health_score:.1f}/100",
            ),
        ]

        return report

    def print_summary(self, report: OverallReport) -> None:
        """Print quality report summary."""
        logger.info("=" * 80)
        logger.info("DATA QUALITY MONITORING REPORT")
        logger.info("=" * 80)

        logger.info("OVERVIEW")
        logger.info("-" * 80)
        logger.info("Total Symbols: %d", report.total_symbols)
        logger.info("Total Candles: %d", report.total_candles)
        if report.date_range[0] and report.date_range[1]:
            logger.info("Date Range: %s to %s", report.date_range[0], report.date_range[1])

        logger.info("HEALTH SCORE: %.1f/100", report.health_score)
        logger.info("-" * 80)

        for metric in report.summary_metrics:
            status_icon = (
                "OK" if metric.status == "PASS" else "WARN" if metric.status == "WARNING" else "FAIL"
            )
            logger.info("[%s] %s: %s", status_icon, metric.name, metric.details)

        problem_symbols = [s for s in report.symbol_reports if s.status != "PASS"]
        if problem_symbols:
            logger.info("SYMBOLS WITH ISSUES (%d)", len(problem_symbols))
            logger.info("-" * 80)

            problem_symbols.sort(key=lambda s: -len(s.issues))
            for sq in problem_symbols[:20]:
                logger.info("%s [%s]", sq.symbol, sq.status)
                for issue in sq.issues:
                    logger.info("  - %s", issue)

        logger.info("=" * 80)
