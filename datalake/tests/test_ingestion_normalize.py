"""Tests for datalake.ingestion.normalize — paise/rupees conversion."""

from __future__ import annotations

import pandas as pd

from datalake.ingestion.normalize import (
    PAISE_THRESHOLD,
    convert_paise_to_rupees,
)


def _make_df(*, values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01"] * len(values)),
            "open": values,
            "high": values,
            "low": values,
            "close": values,
        }
    )


class TestConvertPaiseToRupees:
    def test_auto_mode_converts_large_values(self):
        df = _make_df(values=[1234500.0, 1235000.0])
        result = convert_paise_to_rupees(df)
        assert result["open"].iloc[0] == 12345.0

    def test_auto_mode_skips_small_values(self):
        df = _make_df(values=[100.5, 101.0])
        result = convert_paise_to_rupees(df)
        assert result["open"].iloc[0] == 100.5

    def test_paise_mode_always_converts(self):
        df = _make_df(values=[100.0, 200.0])
        result = convert_paise_to_rupees(df, source_unit="paise")
        assert result["open"].iloc[0] == 1.0
        assert result["close"].iloc[1] == 2.0

    def test_rupees_mode_no_conversion(self):
        df = _make_df(values=[100.0, 200.0])
        result = convert_paise_to_rupees(df, source_unit="rupees")
        assert result["open"].iloc[0] == 100.0

    def test_rupees_mode_warns_on_large_values(self, caplog):
        import logging

        df = _make_df(values=[float(PAISE_THRESHOLD + 1)])
        with caplog.at_level(logging.WARNING):
            convert_paise_to_rupees(df, source_unit="rupees")
        assert "paise_threshold_warning" in caplog.text

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = convert_paise_to_rupees(df)
        assert result.empty

    def test_no_price_columns(self):
        df = pd.DataFrame({"volume": [100], "oi": [0]})
        result = convert_paise_to_rupees(df, source_unit="paise")
        assert "volume" in result.columns
