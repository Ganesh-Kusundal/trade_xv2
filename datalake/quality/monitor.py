"""Data Quality Monitor — automated checks for freshness, completeness, and integrity.

Usage:
    from datalake.monitor import DataQualityMonitor

    monitor = DataQualityMonitor(root="market_data")
    report = monitor.run_checks(timeframe="1m")
    monitor.print_summary(report)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb

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


class DataQualityMonitor:
    """Automated data quality monitoring."""

    def __init__(self, root: str = "market_data") -> None:
        self._root = Path(root)
        self._catalog_path = self._root / "catalog.duckdb"

    def run_checks(self, timeframe: str = "1m") -> OverallReport:
        """Run all quality checks with a single-pass DuckDB query.

        Consolidates basic stats, freshness, completeness, and integrity
        checks into one SQL statement to minimise parquet I/O.
        """
        report = OverallReport()

        # Get parquet pattern
        parquet_dir = self._root / "equities" / "candles" / f"timeframe={timeframe}"
        if not parquet_dir.exists():
            logger.error("Parquet directory not found: %s", parquet_dir)
            return report

        parquet_pattern = str(parquet_dir / "symbol=*" / "data.parquet")

        # Connect to DuckDB
        conn = duckdb.connect(str(self._catalog_path), read_only=True)

        try:
            report = self._run_all_checks(conn, parquet_pattern, timeframe, report)
            report = self._calculate_summary(report)
        finally:
            conn.close()

        return report

    # ------------------------------------------------------------------
    # Single consolidated query replacing the former 4 separate scans:
    #   _check_basic_stats  – global symbol/candle counts & date range  # noqa: RUF003
    #   _check_freshness    – per-symbol latest timestamp & staleness  # noqa: RUF003
    #   _check_completeness – per-symbol avg daily candle count  # noqa: RUF003
    #   _check_integrity    – per-symbol zero-volume & OHLC error counts  # noqa: RUF003
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

        # Pre-compute expected candles per day for completeness check
        expected_per_day: int | None = None
        if timeframe in ("1m", "5m", "15m", "30m"):
            candles_per_hour = 60 // int(timeframe.replace("m", ""))
            expected_per_day = int(candles_per_hour * 6.25)  # 6.25 trading hours

        for sr in symbol_rows:
            symbol = sr["symbol"]
            sq = SymbolQuality(symbol=symbol)

            # ── Freshness ──────────────────────────────────────────
            last_date = sr["last_date"]
            days_old = int(sr["days_old"])

            if days_old <= 1:
                fresh_status = "PASS"
            elif days_old <= 7:
                fresh_status = "WARNING"
            else:
                fresh_status = "FAIL"

            sq.metrics.append(
                QualityMetric(
                    name="freshness",
                    value=days_old,
                    threshold=7.0,
                    status=fresh_status,
                    details=f"Last update: {last_date} ({days_old} days ago)",
                )
            )
            if fresh_status != "PASS":
                sq.issues.append(f"Data is {days_old} days old")

            # ── Completeness ───────────────────────────────────────
            if expected_per_day is not None:
                avg_candles = float(sr["avg_candles_per_day"])
                completeness = (
                    min(avg_candles / expected_per_day, 1.0)
                    if expected_per_day > 0
                    else 0.0
                )

                if completeness >= 0.90:
                    comp_status = "PASS"
                elif completeness >= 0.70:
                    comp_status = "WARNING"
                else:
                    comp_status = "FAIL"

                sq.metrics.append(
                    QualityMetric(
                        name="completeness",
                        value=completeness * 100,
                        threshold=90.0,
                        status=comp_status,
                        details=(
                            f"{avg_candles:.0f}/{expected_per_day} candles/day"
                            f" ({completeness * 100:.1f}%)"
                        ),
                    )
                )
                if comp_status != "PASS":
                    sq.issues.append(
                        f"Only {completeness * 100:.0f}% complete"
                        f" ({avg_candles:.0f}/{expected_per_day} candles/day)"
                    )

            # ── Integrity: zero volume ─────────────────────────────
            total = int(sr["total_candles"])
            zero_vol = int(sr["zero_volume"])
            ohlc_err = int(sr["ohlc_errors"])

            zero_pct = (zero_vol / total * 100) if total > 0 else 0.0

            if zero_pct < 1:
                zv_status = "PASS"
            elif zero_pct < 10:
                zv_status = "WARNING"
            else:
                zv_status = "FAIL"

            sq.metrics.append(
                QualityMetric(
                    name="zero_volume",
                    value=zero_pct,
                    threshold=10.0,
                    status=zv_status,
                    details=f"{zero_vol:,}/{total:,} ({zero_pct:.1f}%)",
                )
            )
            if zv_status != "PASS":
                sq.issues.append(f"{zero_pct:.1f}% zero volume bars")

            # ── Integrity: OHLC consistency ────────────────────────
            if ohlc_err == 0:
                sq.metrics.append(
                    QualityMetric(
                        name="ohlc_integrity",
                        value=0,
                        threshold=0,
                        status="PASS",
                        details="No errors",
                    )
                )
            else:
                error_pct = ohlc_err / total * 100
                sq.metrics.append(
                    QualityMetric(
                        name="ohlc_integrity",
                        value=error_pct,
                        threshold=0,
                        status="FAIL",
                        details=f"{ohlc_err} errors ({error_pct:.2f}%)",
                    )
                )
                sq.issues.append(f"{ohlc_err} OHLC errors")

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
        print("=" * 80)
        print("DATA QUALITY MONITORING REPORT")
        print("=" * 80)

        print("\n📊 OVERVIEW")
        print("-" * 80)
        print(f"Total Symbols: {report.total_symbols:,}")
        print(f"Total Candles: {report.total_candles:,}")
        if report.date_range[0] and report.date_range[1]:
            print(f"Date Range: {report.date_range[0]} to {report.date_range[1]}")

        print(f"\n📈 HEALTH SCORE: {report.health_score:.1f}/100")
        print("-" * 80)

        for metric in report.summary_metrics:
            status_icon = (
                "✅" if metric.status == "PASS" else "⚠️" if metric.status == "WARNING" else "❌"
            )
            print(f"{status_icon} {metric.name}: {metric.details}")

        # Symbols with issues
        problem_symbols = [s for s in report.symbol_reports if s.status != "PASS"]
        if problem_symbols:
            print(f"\n⚠️  SYMBOLS WITH ISSUES ({len(problem_symbols)})")
            print("-" * 80)

            # Show worst first
            problem_symbols.sort(key=lambda s: -len(s.issues))
            for sq in problem_symbols[:20]:  # Top 20
                print(f"\n{sq.symbol} [{sq.status}]")
                for issue in sq.issues:
                    print(f"  - {issue}")

        print("\n" + "=" * 80)
