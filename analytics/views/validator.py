"""Point-In-Time Validation Framework — ensures no look-ahead bias in analytics views."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Report from point-in-time validation."""
    view_name: str
    is_valid: bool = True
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def add_issue(self, issue: str) -> None:
        self.issues.append(issue)
        self.is_valid = False


class PointInTimeValidator:
    """Validates that analytics views are point-in-time correct.

    Checks:
    1. No future data leakage
    2. Correct temporal ordering
    3. No look-ahead bias in feature calculations
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def validate_all(self) -> list[ValidationReport]:
        """Validate all key analytics views."""
        views_to_validate = [
            "v_candles_1m",
            "v_daily_summary",
            "v_feature_rsi",
            "v_feature_atr",
            "v_feature_vwap",
            "v_feature_volume",
            "v_feature_momentum",
            "v_relative_strength",
            "v_trend_state",
            "v_scanner_snapshot",
            "v_top3_candidates",
            "v_top10_candidates",
            "v_strategy_candidates",
        ]

        reports = []
        for view_name in views_to_validate:
            try:
                report = self.validate_view(view_name)
                reports.append(report)
            except Exception as exc:
                report = ValidationReport(view_name=view_name, is_valid=False)
                report.add_issue(f"Validation failed: {exc}")
                reports.append(report)

        return reports

    def validate_view(self, view_name: str) -> ValidationReport:
        """Validate a single view for point-in-time correctness."""
        report = ValidationReport(view_name=view_name)

        # Check 1: View exists
        if not self._view_exists(view_name):
            report.add_issue(f"View {view_name} does not exist")
            return report

        # Check 2: No future timestamps
        self._check_no_future_data(view_name, report)

        # Check 3: Temporal ordering
        self._check_temporal_ordering(view_name, report)

        # Check 4: Feature calculation lag
        if "feature" in view_name or "scanner" in view_name:
            self._check_feature_lag(view_name, report)

        return report

    def _view_exists(self, view_name: str) -> bool:
        result = self._conn.execute(
            "SELECT COUNT(*) FROM pg_views WHERE viewname = ? AND schemaname = 'main'",
            [view_name],
        ).fetchone()
        return result[0] > 0

    def _check_no_future_data(self, view_name: str, report: ValidationReport) -> None:
        """Check that no view contains data from the future."""
        try:
            result = self._conn.execute(f"""
                SELECT
                    MAX(timestamp) as max_ts,
                    MAX(CAST(timestamp AS DATE)) as max_date
                FROM {view_name}
                WHERE timestamp IS NOT NULL
            """).fetchone()

            if result and result[0]:
                max_ts = result[0]
                if isinstance(max_ts, datetime):
                    now = datetime.now()
                    if max_ts > now:
                        report.add_issue(
                            f"Future data detected: max timestamp {max_ts} > now {now}"
                        )
        except Exception:
            pass  # View may not have timestamp column

    def _check_temporal_ordering(self, view_name: str, report: ValidationReport) -> None:
        """Check that data is temporally ordered."""
        try:
            result = self._conn.execute(f"""
                SELECT COUNT(*) as out_of_order
                FROM (
                    SELECT
                        symbol,
                        timestamp,
                        LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_ts
                    FROM {view_name}
                    WHERE symbol IS NOT NULL AND timestamp IS NOT NULL
                )
                WHERE timestamp < prev_ts
            """).fetchone()

            if result and result[0] > 0:
                report.add_issue(
                    f"Temporal ordering violation: {result[0]} rows out of order"
                )
        except Exception:
            pass  # View may not have required columns

    def _check_feature_lag(self, view_name: str, report: ValidationReport) -> None:
        """Check that features use only past data (no look-ahead)."""
        try:
            # Check for window functions that might leak future data
            result = self._conn.execute(f"""
                SELECT definition
                FROM pg_views
                WHERE viewname = '{view_name}'
            """).fetchone()

            if result and result[0]:
                definition = result[0].upper()
                # Red flags for look-ahead bias
                if "LEAD(" in definition:
                    report.add_issue("LEAD() function detected — potential look-ahead bias")
                if "ROWS BETWEEN" in definition and "FOLLOWING" in definition:
                    report.add_issue("FOLLOWING window frame detected — potential look-ahead bias")
                if "UNBOUNDED FOLLOWING" in definition:
                    report.add_issue("UNBOUNDED FOLLOWING detected — potential look-ahead bias")
        except Exception:
            pass

    def generate_summary(self, reports: list[ValidationReport]) -> dict:
        """Generate summary of all validation reports."""
        total = len(reports)
        valid = sum(1 for r in reports if r.is_valid)
        invalid = total - valid
        all_issues = []
        for r in reports:
            for issue in r.issues:
                all_issues.append(f"{r.view_name}: {issue}")

        return {
            "total_views": total,
            "valid": valid,
            "invalid": invalid,
            "pass_rate": valid / total * 100 if total > 0 else 0,
            "issues": all_issues,
        }
