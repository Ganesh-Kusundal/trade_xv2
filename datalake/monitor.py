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
        """Run all quality checks."""
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
            # Basic statistics
            report = self._check_basic_stats(conn, parquet_pattern, report)

            # Freshness checks
            report = self._check_freshness(conn, parquet_pattern, report)

            # Completeness checks
            report = self._check_completeness(conn, parquet_pattern, timeframe, report)

            # Integrity checks
            report = self._check_integrity(conn, parquet_pattern, report)

            # Summary metrics
            report = self._calculate_summary(report)

        finally:
            conn.close()

        return report

    def _check_basic_stats(
        self, conn: duckdb.DuckDBPyConnection, pattern: str, report: OverallReport
    ) -> OverallReport:
        """Check basic statistics."""
        result = conn.execute(
            """
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                COUNT(*) as total_candles,
                MIN(timestamp)::DATE as min_date,
                MAX(timestamp)::DATE as max_date
            FROM read_parquet(?)
        """,
            [pattern],
        ).fetchone()

        report.total_symbols = result[0]
        report.total_candles = result[1]
        report.date_range = (result[2], result[3])

        return report

    def _check_freshness(
        self, conn: duckdb.DuckDBPyConnection, pattern: str, report: OverallReport
    ) -> OverallReport:
        """Check data freshness for each symbol."""
        date.today()

        # Get latest date per symbol
        result = conn.execute(
            """
            SELECT
                symbol,
                MAX(timestamp)::DATE as latest_date,
                DATEDIFF('day', MAX(timestamp)::DATE, CURRENT_DATE) as days_old
            FROM read_parquet(?)
            GROUP BY symbol
        """,
            [pattern],
        ).fetchall()

        for symbol, latest_date, days_old in result:
            sq = SymbolQuality(symbol=symbol)

            # Freshness metric
            if days_old <= 1:
                status = "PASS"
            elif days_old <= 7:
                status = "WARNING"
            else:
                status = "FAIL"

            sq.metrics.append(
                QualityMetric(
                    name="freshness",
                    value=days_old,
                    threshold=7.0,
                    status=status,
                    details=f"Last update: {latest_date} ({days_old} days ago)",
                )
            )

            if status != "PASS":
                sq.issues.append(f"Data is {days_old} days old")

            report.symbol_reports.append(sq)

        return report

    def _check_completeness(
        self,
        conn: duckdb.DuckDBPyConnection,
        pattern: str,
        timeframe: str,
        report: OverallReport,
    ) -> OverallReport:
        """Check intraday completeness."""
        if timeframe not in ("1m", "5m", "15m", "30m"):
            return report

        # Calculate expected candles per day
        candles_per_hour = 60 // int(timeframe.replace("m", "").replace("h", "60"))
        expected_per_day = int(candles_per_hour * 6.25)  # 6.25 trading hours

        # Get candle count per symbol per day
        result = conn.execute(
            """
            SELECT
                symbol,
                SUM(daily_count) as total_candles,
                COUNT(*) as trading_days,
                ROUND(AVG(daily_count), 1) as avg_candles_per_day
            FROM (
                SELECT
                    symbol,
                    DATE_TRUNC('day', timestamp) as day,
                    COUNT(*) as daily_count
                FROM read_parquet(?)
                GROUP BY symbol, DATE_TRUNC('day', timestamp)
            )
            GROUP BY symbol
        """,
            [pattern],
        ).fetchall()

        for symbol, _total_candles, _trading_days, avg_candles in result:
            # Find or create symbol report
            sq = next((s for s in report.symbol_reports if s.symbol == symbol), None)
            if sq is None:
                sq = SymbolQuality(symbol=symbol)
                report.symbol_reports.append(sq)

            # Completeness metric
            completeness = min(avg_candles / expected_per_day, 1.0) if expected_per_day > 0 else 0

            if completeness >= 0.90:
                status = "PASS"
            elif completeness >= 0.70:
                status = "WARNING"
            else:
                status = "FAIL"

            sq.metrics.append(
                QualityMetric(
                    name="completeness",
                    value=completeness * 100,
                    threshold=90.0,
                    status=status,
                    details=f"{avg_candles:.0f}/{expected_per_day} candles/day ({completeness * 100:.1f}%)",
                )
            )

            if status != "PASS":
                sq.issues.append(
                    f"Only {completeness * 100:.0f}% complete ({avg_candles:.0f}/{expected_per_day} candles/day)"
                )

        return report

    def _check_integrity(
        self, conn: duckdb.DuckDBPyConnection, pattern: str, report: OverallReport
    ) -> OverallReport:
        """Check data integrity (zero volume, OHLC errors)."""
        result = conn.execute(
            """
            SELECT
                symbol,
                COUNT(*) as total_candles,
                SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) as zero_volume,
                SUM(CASE WHEN high < low THEN 1 ELSE 0 END) as ohlc_errors
            FROM read_parquet(?)
            GROUP BY symbol
        """,
            [pattern],
        ).fetchall()

        for symbol, total_candles, zero_volume, ohlc_errors in result:
            # Find or create symbol report
            sq = next((s for s in report.symbol_reports if s.symbol == symbol), None)
            if sq is None:
                sq = SymbolQuality(symbol=symbol)
                report.symbol_reports.append(sq)

            # Zero volume metric
            zero_pct = (zero_volume / total_candles * 100) if total_candles > 0 else 0

            if zero_pct < 1:
                status = "PASS"
            elif zero_pct < 10:
                status = "WARNING"
            else:
                status = "FAIL"

            sq.metrics.append(
                QualityMetric(
                    name="zero_volume",
                    value=zero_pct,
                    threshold=10.0,
                    status=status,
                    details=f"{zero_volume:,}/{total_candles:,} ({zero_pct:.1f}%)",
                )
            )

            if status != "PASS":
                sq.issues.append(f"{zero_pct:.1f}% zero volume bars")

            # OHLC errors metric
            if ohlc_errors == 0:
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
                error_pct = ohlc_errors / total_candles * 100
                sq.metrics.append(
                    QualityMetric(
                        name="ohlc_integrity",
                        value=error_pct,
                        threshold=0,
                        status="FAIL",
                        details=f"{ohlc_errors} errors ({error_pct:.2f}%)",
                    )
                )
                sq.issues.append(f"{ohlc_errors} OHLC errors")

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
