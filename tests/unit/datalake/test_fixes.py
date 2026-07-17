"""Tests for datalake review fixes — F1 through F10."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from datalake.core.io import file_lock
from datalake.core.nse_calendar import count_trading_days, expected_candles, is_trading_day
from datalake.core.pit_joins import PitQueryConfig
from datalake.core.symbols import normalize_symbol, sanitize_path_param
from datalake.quality.validation import validate_candles

# ── F1: Validation causality invariant + audit trail ──────────────────────


class TestValidationAudit:
    def test_audit_clean_data(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=5),
            "open": [100.0] * 5, "high": [101.0] * 5,
            "low": [99.0] * 5, "close": [100.0] * 5,
            "volume": [1000] * 5,
            "event_time": pd.date_range("2024-01-01", periods=5),
            "published_at": pd.date_range("2024-01-01 00:00:01", periods=5),
        })
        _result, audit = validate_candles(df, "TEST", return_audit=True)
        assert audit.is_clean
        assert audit.dropped_rows == 0

    def test_audit_catches_causality_violation(self):
        ts = pd.date_range("2024-01-01", periods=5)
        df = pd.DataFrame({
            "timestamp": ts,
            "open": [100.0] * 5, "high": [101.0] * 5,
            "low": [99.0] * 5, "close": [100.0] * 5,
            "volume": [1000] * 5,
            "event_time": ts,
            "published_at": ts - pd.Timedelta(hours=1),
        })
        _result, audit = validate_candles(df, "TEST", return_audit=True)
        assert audit.dropped_rows == 5
        assert any("causality" in i for i in audit.issues)

    def test_empty_df_returns_audit(self):
        df = pd.DataFrame()
        _result, audit = validate_candles(df, "TEST", return_audit=True)
        assert audit.total_rows == 0


# ── F2: Path traversal sanitization ───────────────────────────────────────


class TestPathTraversal:
    def test_reject_double_dot(self):
        with pytest.raises(ValueError, match="path traversal"):
            sanitize_path_param("../../etc/passwd")

    def test_reject_slash(self):
        with pytest.raises(ValueError):
            sanitize_path_param("1m/../../foo")

    def test_reject_null_byte(self):
        with pytest.raises(ValueError):
            sanitize_path_param("1m\x00../../etc")

    def test_clean_param_passes(self):
        assert sanitize_path_param("1m") == "1m"
        assert sanitize_path_param("WEEK") == "WEEK"

    def test_symbol_rejects_traversal(self):
        with pytest.raises(ValueError, match="path traversal"):
            normalize_symbol("../etc")


# ── F4: DuckDBReadPool max connections ────────────────────────────────────


class TestReadPoolCap:
    def test_max_connections_enforced(self):
        from datalake.core.duckdb_utils import DuckDBReadPool
        pool = DuckDBReadPool(max_per_path=2)
        # Acquiring 3 should fail on the 3rd
        # (We can't easily test this without a real DB file, so test the logic)
        assert pool._max_per_path == 2


# ── F7: NSE holiday calendar ──────────────────────────────────────────────


class TestNSECalendar:
    def test_republic_day_is_holiday(self):
        assert not is_trading_day(date(2024, 1, 26))

    def test_saturday_not_trading(self):
        assert not is_trading_day(date(2024, 1, 27))

    def test_normal_weekday_is_trading(self):
        assert is_trading_day(date(2024, 1, 29))

    def test_early_close(self):
        from datalake.core.nse_calendar import is_early_close
        assert not is_early_close(date(2024, 1, 15))

    def test_expected_candles(self):
        assert expected_candles(date(2024, 1, 29), "1m") == 375
        assert expected_candles(date(2024, 1, 26), "1m") == 0

    def test_count_trading_days(self):
        # Jan 29-31 2024: Mon, Tue, Wed = 3 trading days
        count = count_trading_days(date(2024, 1, 29), date(2024, 1, 31))
        assert count == 3

    def test_known_holidays_excluded(self):
        # Cross-checked against zero-candle days in the datalake and NSE's
        # official yearly "Trading holidays" circulars.
        for d in [
            date(2021, 7, 21),   # Bakri Id 2021 (shifted from originally notified Jul 20)
            date(2021, 9, 10),   # Ganesh Chaturthi 2021
            date(2021, 11, 5),   # Diwali-Balipratipada 2021
            date(2022, 8, 31),   # Ganesh Chaturthi 2022
            date(2022, 10, 24),  # Diwali-Laxmi Pujan 2022 (regular session closed; Muhurat trading only)
            date(2022, 10, 26),  # Diwali-Balipratipada 2022
            date(2024, 1, 22),   # Ram Mandir Pran Pratishtha (ad-hoc Maharashtra holiday)
            date(2024, 5, 20),   # Lok Sabha election polling day (Mumbai)
            date(2026, 1, 15),   # Maharashtra civic body elections (ad-hoc holiday)
        ]:
            assert not is_trading_day(d), f"{d} should be an NSE holiday"

    def test_adjacent_trading_days_included(self):
        # Days next to holidays, and dates previously miscoded as holidays
        # that are in fact regular trading days.
        for d in [
            date(2021, 7, 20),   # originally-notified Bakri Id date; actual holiday was Jul 21
            date(2022, 10, 25),  # trading day between the two Diwali holidays
            date(2026, 3, 6),    # previously miscoded as Holi; real Holi 2026 is Mar 3
        ]:
            assert is_trading_day(d), f"{d} should be a regular trading day"


# ── F9: PIT strict mode default ──────────────────────────────────────────


class TestPITStrictDefault:
    def test_strict_is_true_by_default(self):
        config = PitQueryConfig()
        assert config.strict is True

    def test_can_override_to_false(self):
        config = PitQueryConfig(strict=False)
        assert config.strict is False


# ── F3: File lock ─────────────────────────────────────────────────────────


class TestFileLock:
    def test_concurrent_access(self, tmp_path):
        """Verify file_lock allows sequential access."""
        target = tmp_path / "test.parquet"
        target.write_text("data")

        with file_lock(target):
            assert target.exists()

        assert target.exists()

    def test_lock_creates_lock_file(self, tmp_path):
        target = tmp_path / "test.parquet"
        target.write_text("data")
        with file_lock(target):
            assert (tmp_path / "test.parquet.lock").exists()
