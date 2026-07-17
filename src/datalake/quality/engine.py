"""Data Quality Engine — checks for missing candles, duplicates, gaps, OI anomalies."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _date_range(start: date, end: date) -> list[date]:
    """Yield all dates from start to end inclusive."""
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


@dataclass
class QualityReport:
    """Data quality report for a symbol."""

    symbol: str = ""
    timeframe: str = "1m"
    total_rows: int = 0
    missing_candles: int = 0
    duplicate_candles: int = 0
    gap_days: int = 0
    min_date: date | None = None
    max_date: date | None = None
    completeness_pct: float = 0.0
    status: str = "OK"
    issues: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"=== Quality Report: {self.symbol} ({self.timeframe}) ===",
            f"Status: {self.status}",
            f"Rows: {self.total_rows:,}",
            f"Date range: {self.min_date} to {self.max_date}",
            f"Missing candles: {self.missing_candles}",
            f"Duplicate candles: {self.duplicate_candles}",
            f"Gap days: {self.gap_days}",
            f"Completeness: {self.completeness_pct:.1f}%",
        ]
        if self.issues:
            lines.append("\nIssues:")
            for issue in self.issues[:20]:
                lines.append(f"  - {issue}")
        return "\n".join(lines)


class DataQualityEngine:
    """Validates data quality for symbols in the data lake."""

    def __init__(self, root: str | None = None, catalog=None) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS
            root = DEFAULT_DATA_PATHS.lake_root
        self._root = Path(root)
        self._catalog = catalog

    def check(self, symbol: str, timeframe: str = "1m") -> QualityReport:
        """Run all quality checks for a symbol."""
        report = QualityReport(symbol=symbol, timeframe=timeframe)

        from datalake.core.paths import symbol_partition_path

        parquet_path = symbol_partition_path(str(self._root), symbol, timeframe)
        if not parquet_path.exists():
            report.status = "MISSING"
            report.issues.append(f"No data file found: {parquet_path}")
            return report

        try:
            df = pd.read_parquet(parquet_path)
        except Exception as exc:
            report.status = "ERROR"
            report.issues.append(f"Failed to read Parquet: {exc}")
            return report

        if df.empty:
            report.status = "EMPTY"
            report.issues.append("File is empty")
            return report

        report.total_rows = len(df)

        # Date range
        ts = pd.to_datetime(df["timestamp"])
        report.min_date = ts.min().date()
        report.max_date = ts.max().date()

        # Duplicates
        dup_count = df.duplicated(subset=["timestamp"]).sum()
        report.duplicate_candles = int(dup_count)
        if dup_count > 0:
            report.issues.append(f"{dup_count} duplicate timestamps")
            report.status = "WARNING"

        # Missing candles (check trading days)
        if timeframe in ("1m", "5m", "15m", "30m", "1h"):
            self._check_intraday_gaps(ts, timeframe, report)
        else:
            self._check_daily_gaps(ts, report)

        # OHLC consistency — validate price relationships
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            bad_hl = (df["high"] < df["low"]).sum()
            if bad_hl > 0:
                report.issues.append(f"{bad_hl} rows with high < low")
                report.status = "WARNING"
            bad_close_high = (df["close"] > df["high"]).sum()
            if bad_close_high > 0:
                report.issues.append(f"{bad_close_high} rows with close > high")
                report.status = "WARNING"
            bad_close_low = (df["close"] < df["low"]).sum()
            if bad_close_low > 0:
                report.issues.append(f"{bad_close_low} rows with close < low")
                report.status = "WARNING"
            # Zero-range candles (open=high=low=close) may indicate missing data
            zero_range = (
                (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])
            ).sum()
            if zero_range > 0:
                report.issues.append(f"{zero_range} zero-range candles (possible stale data)")

        # Zero volume
        if "volume" in df.columns:
            zero_vol = (df["volume"] == 0).sum()
            if zero_vol > 0:
                report.issues.append(f"{zero_vol} rows with zero volume")

        # Completeness (uses exchange calendar when available)
        if report.gap_days > 0 and report.min_date and report.max_date:
            try:
                from datalake.exchange_registry import get_active_adapter
                calendar = get_active_adapter().calendar
                expected_trading_days = sum(
                    1 for d in _date_range(report.min_date, report.max_date)
                    if calendar.is_trading_day(d)
                )
            except Exception:
                total_days = (report.max_date - report.min_date).days
                expected_trading_days = int(total_days * 5 / 7)
            if expected_trading_days > 0:
                report.completeness_pct = max(
                    0, 100 - (report.gap_days / expected_trading_days * 100)
                )

        # Record in catalog
        if self._catalog:
            self._catalog.record_quality(
                symbol=symbol,
                total_rows=report.total_rows,
                missing_candles=report.missing_candles,
                duplicate_candles=report.duplicate_candles,
                gap_days=report.gap_days,
                min_date=report.min_date,
                max_date=report.max_date,
                completeness_pct=report.completeness_pct,
                status=report.status,
                timeframe=timeframe,
            )

        return report

    def check_universe(
        self, universe: str = "NIFTY500", timeframe: str = "1m"
    ) -> list[QualityReport]:
        """Check quality for all symbols in a universe (I-17: DuckDB first)."""
        from datalake.core.schema import load_universe

        symbols = load_universe(universe, catalog=self._catalog)
        if not symbols:
            return []

        reports = []
        for symbol in symbols:
            report = self.check(symbol, timeframe)
            reports.append(report)

        return reports

    def _check_intraday_gaps(self, ts: pd.Series, timeframe: str, report: QualityReport) -> None:
        """Check for gaps in intraday data."""
        delta_map = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
        }
        delta = delta_map.get(timeframe)
        if delta is None:
            return

        sorted_ts = ts.sort_values()
        gaps = 0
        for i in range(1, len(sorted_ts)):
            diff = sorted_ts.iloc[i] - sorted_ts.iloc[i - 1]
            if diff > delta * 2:
                gaps += int(diff / delta) - 1

        report.missing_candles = gaps
        if gaps > 0:
            report.issues.append(f"{gaps} missing intraday candles")
            report.status = "WARNING"

    def _check_daily_gaps(self, ts: pd.Series, report: QualityReport) -> None:
        """Check for gaps in daily data, using exchange calendar when available."""
        sorted_ts = ts.sort_values()
        dates = sorted_ts.dt.date.unique()
        if len(dates) < 2:
            return

        dates_sorted = sorted(dates)

        try:
            from datalake.exchange_registry import get_active_adapter
            calendar = get_active_adapter().calendar
            expected = [
                d for d in _date_range(dates_sorted[0], dates_sorted[-1])
                if calendar.is_trading_day(d)
            ]
            expected_set = set(expected)
            actual_set = set(dates_sorted)
            gaps = len(expected_set - actual_set)
        except Exception:
            gaps = 0
            for i in range(1, len(dates_sorted)):
                diff = (dates_sorted[i] - dates_sorted[i - 1]).days
                if diff > 4:
                    gaps += diff - 1

        report.gap_days = gaps
        if gaps > 0:
            report.issues.append(f"{gaps} gap days detected")
            report.status = "WARNING"
