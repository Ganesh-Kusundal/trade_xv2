"""Tests for DataQualityValidator — missing candles, duplicates, OI/volume anomalies, timestamps."""

import pandas as pd

from brokers.common.services.data_validator import DataQualityValidator, ValidationReport


class TestValidationReport:
    def test_add_critical_fails(self):
        report = ValidationReport(symbol="TEST", total_rows=100)
        report.add(
            type(
                "Issue",
                (),
                {
                    "category": "test",
                    "severity": "critical",
                    "message": "bad",
                    "row_index": None,
                    "column": "",
                },
            )()
        )
        assert report.passed is False
        assert report.critical_count == 1

    def test_add_warning_stays_passed(self):
        report = ValidationReport(symbol="TEST", total_rows=100)
        report.add(
            type(
                "Issue",
                (),
                {
                    "category": "test",
                    "severity": "warning",
                    "message": "ok",
                    "row_index": None,
                    "column": "",
                },
            )()
        )
        assert report.passed is True
        assert report.warning_count == 1

    def test_summary(self):
        report = ValidationReport(
            symbol="TEST",
            total_rows=10,
            total_issues=1,
            critical_count=1,
            warning_count=0,
            info_count=0,
            passed=False,
        )
        s = report.summary()
        assert "TEST" in s
        assert "FAILED" in s


class TestDataQualityValidator:
    def _make_df(self, n=100, start="2026-01-01", freq="1D", with_oi=True, with_volume=True):
        dates = pd.date_range(start, periods=n, freq=freq)
        df = pd.DataFrame(
            {
                "timestamp": dates,
                "open": [100 + i * 0.5 for i in range(n)],
                "high": [101 + i * 0.5 for i in range(n)],
                "low": [99 + i * 0.5 for i in range(n)],
                "close": [100.5 + i * 0.5 for i in range(n)],
                "volume": [10000 + i * 100 for i in range(n)],
            }
        )
        if with_oi:
            df["oi"] = [50000 + i * 50 for i in range(n)]
        return df

    def test_validate_empty(self):
        report = DataQualityValidator().validate(pd.DataFrame(), symbol="EMPTY")
        assert report.passed is False
        assert report.critical_count >= 1

    def test_validate_clean_data(self):
        df = self._make_df()
        report = DataQualityValidator().validate(df, symbol="CLEAN", timeframe="1d")
        assert report.passed is True
        assert report.total_rows == 100

    def test_detect_missing_candles(self):
        df = self._make_df(n=10)
        # Remove rows 4 and 5 to create a 2-candle gap
        df = df.drop([4, 5]).reset_index(drop=True)
        validator = DataQualityValidator()
        issues = validator.check_missing_candles(df, timeframe="1d")
        assert len(issues) >= 1
        assert any("Missing" in i.message for i in issues)

    def test_detect_duplicates(self):
        df = self._make_df(n=10)
        # Duplicate row 3
        dup = df.iloc[[3]].copy()
        df = pd.concat([df, dup], ignore_index=True)
        validator = DataQualityValidator()
        issues = validator.check_duplicates(df)
        assert len(issues) >= 1
        assert any("duplicate" in i.message.lower() for i in issues)

    def test_detect_ohlc_inconsistency(self):
        df = self._make_df(n=10)
        # Set high < low on row 2
        df.loc[2, "high"] = 50
        df.loc[2, "low"] = 200
        validator = DataQualityValidator()
        issues = validator.check_duplicates(df)
        assert any("OHLC" in i.message for i in issues)

    def test_detect_oi_anomalies(self):
        df = self._make_df(n=50)
        # Spike OI on row 25 (should be detected by z-score)
        df.loc[25, "oi"] = int(df["oi"].mean() + 20 * df["oi"].std())
        validator = DataQualityValidator()
        issues = validator.check_oi_anomalies(df, z_threshold=3.0)
        assert len(issues) >= 1

    def test_detect_negative_oi(self):
        df = self._make_df(n=20)
        df.loc[5, "oi"] = -100
        validator = DataQualityValidator()
        issues = validator.check_oi_anomalies(df)
        assert any("negative" in i.message.lower() for i in issues)

    def test_detect_oi_wipe(self):
        df = self._make_df(n=20)
        df.loc[10, "oi"] = int(df.loc[9, "oi"] * 0.05)  # 95% drop
        validator = DataQualityValidator()
        issues = validator.check_oi_anomalies(df)
        assert any("wipe" in i.message.lower() for i in issues)

    def test_detect_zero_volume(self):
        df = self._make_df(n=20)
        df.loc[5, "volume"] = 0
        df.loc[8, "volume"] = 0
        validator = DataQualityValidator()
        issues = validator.check_volume_anomalies(df)
        assert any("zero volume" in i.message.lower() for i in issues)

    def test_detect_volume_anomalies(self):
        df = self._make_df(n=50)
        df.loc[25, "volume"] = int(df["volume"].mean() + 20 * df["volume"].std())
        validator = DataQualityValidator()
        issues = validator.check_volume_anomalies(df, z_threshold=3.0)
        assert len(issues) >= 1

    def test_detect_out_of_order_timestamps(self):
        df = self._make_df(n=10)
        # Swap rows 3 and 7
        df.iloc[3], df.iloc[7] = df.iloc[7].copy(), df.iloc[3].copy()
        validator = DataQualityValidator()
        issues = validator.check_timestamps(df, timeframe="1d")
        assert any("out of order" in i.message.lower() for i in issues)

    def test_detect_invalid_timestamps(self):
        df = self._make_df(n=10)
        # Force timestamp column to object type so we can inject NaT
        df["timestamp"] = df["timestamp"].astype(object)
        df.loc[3, "timestamp"] = None
        validator = DataQualityValidator()
        issues = validator.check_timestamps(df, timeframe="1d")
        assert any(
            "invalid" in i.message.lower() or "unparseable" in i.message.lower() for i in issues
        )

    def test_validate_all_checks(self):
        df = self._make_df(n=50)
        df.loc[25, "volume"] = int(df["volume"].mean() + 20 * df["volume"].std())  # volume anomaly
        report = DataQualityValidator().validate(df, symbol="MIXED", timeframe="1d")
        assert report.total_issues >= 1
        assert report.warning_count >= 1

    def test_validate_no_oi_column(self):
        df = self._make_df(n=20, with_oi=False)
        report = DataQualityValidator().validate(df, symbol="NO_OI", check_oi=True)
        assert report.passed is True  # no OI = no OI issues

    def test_validate_intraday_checks_weekend(self):
        """Intraday timestamps on weekends should be flagged."""
        dates = pd.date_range("2026-01-03", periods=5, freq="1h")  # Sat/Sun
        df = pd.DataFrame(
            {
                "timestamp": dates,
                "open": range(5),
                "high": range(5),
                "low": range(5),
                "close": range(5),
                "volume": range(5),
            }
        )
        validator = DataQualityValidator()
        issues = validator.check_timestamps(df, timeframe="1h")
        assert any("weekend" in i.message.lower() for i in issues)

    def test_validate_skip_when_unknown_timeframe(self):
        df = self._make_df(n=10)
        validator = DataQualityValidator()
        issues = validator.check_missing_candles(df, timeframe="unknown")
        assert any("Unknown timeframe" in i.message for i in issues)
