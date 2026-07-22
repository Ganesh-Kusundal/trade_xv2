"""Tests for option_format module and sync_options function."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from datalake.core.option_format import (
    CANONICAL_COLUMNS,
    convert_format,
    convert_from_dhan_rolling,
    make_option_symbol,
    map_expiry_code_to_date,
    strike_offset_to_dhan_strike,
)
from datalake.core.schema import ARROW_SCHEMA
from datalake.ingestion.options_sync_manifest import OptionsSyncManifestEntry, write_options_sync_manifest
from datalake.ingestion.sync_options import _get_watermark_date, sync_options

# ============================================================
# Tests for option_format module
# ============================================================


class TestMakeOptionSymbol:
    def test_basic(self) -> None:
        assert make_option_symbol("NIFTY", "WEEK", 1, -2, "CALL") == "NIFTY_WEEK_1_-2_CALL"

    def test_with_positive_offset(self) -> None:
        assert make_option_symbol("BANKNIFTY", "MONTH", 1, 5, "PUT") == "BANKNIFTY_MONTH_1_5_PUT"

    def test_with_zero_offset(self) -> None:
        assert make_option_symbol("NIFTY", "WEEK", 2, 0, "CALL") == "NIFTY_WEEK_2_0_CALL"

    def test_int_casting(self) -> None:
        # expiry_code and strike_offset may come in as numpy int64
        assert make_option_symbol("NIFTY", "WEEK", 1, -2, "CALL") == "NIFTY_WEEK_1_-2_CALL"


class TestMapExpiryCodeToDate:
    def test_week_code1_monday(self) -> None:
        # 2026-03-02 00:00 UTC = Monday → next Thursday = 2026-03-05
        ts = int(pd.Timestamp("2026-03-02").timestamp() * 1000)
        assert map_expiry_code_to_date("NIFTY", "WEEK", 1, ts) == "2026-03-05"

    def test_week_code2_monday(self) -> None:
        ts = int(pd.Timestamp("2026-03-02").timestamp() * 1000)
        assert map_expiry_code_to_date("NIFTY", "WEEK", 2, ts) == "2026-03-12"

    def test_week_thursday(self) -> None:
        # 2026-03-05 00:00 UTC = Thursday → next Thursday = 2026-03-12 (not same day)
        ts = int(pd.Timestamp("2026-03-05").timestamp() * 1000)
        assert map_expiry_code_to_date("NIFTY", "WEEK", 1, ts) == "2026-03-12"

    def test_month_last_thursday(self) -> None:
        # March 2026: last Thursday = 2026-03-26
        ts = int(pd.Timestamp("2026-03-02").timestamp() * 1000)
        assert map_expiry_code_to_date("NIFTY", "MONTH", 1, ts) == "2026-03-26"

    def test_banknifty_uses_same_rules(self) -> None:
        ts = int(pd.Timestamp("2026-03-02").timestamp() * 1000)
        assert map_expiry_code_to_date("BANKNIFTY", "WEEK", 1, ts) == "2026-03-05"

    def test_unknown_underlying_returns_ref_date(self) -> None:
        ts = int(pd.Timestamp("2026-03-02 12:00").timestamp() * 1000)
        d = map_expiry_code_to_date("UNKNOWN", "WEEK", 1, ts)
        assert d == "2026-03-02"  # ref date in IST


class TestConvertFormat:
    def test_paise_to_rupees(self) -> None:
        raw = pd.DataFrame(
            {
                "open_paisa": [10000, 20000],
                "high_paisa": [10500, 21000],
                "low_paisa": [9500, 19000],
                "close_paisa": [10200, 20500],
                "spot_paisa": [2360000, 5500000],
                "strike_paisa": [2350000, 5500000],
                "bar_time_ms": [1772496000000, 1772496000000],
                "underlying": ["NIFTY", "BANKNIFTY"],
                "expiry_kind": ["WEEK", "WEEK"],
                "expiry_code": [1, 1],
                "strike_offset": [-2, 5],
                "option_type": ["CALL", "PUT"],
                "interval_min": [5, 5],
                "volume": [1000, 2000],
                "iv": [15.0, 16.0],
                "oi": [5000, 8000],
                "ingested_at_ms": [1772496000000, 1772496000000],
            }
        )
        out = convert_format(raw)
        assert out["open"].iloc[0] == 100.0
        assert out["close"].iloc[1] == 205.0
        assert out["spot"].iloc[0] == 23600.0
        assert out["strike"].iloc[0] == 23500.0

    def test_timestamp_ist_no_tz(self) -> None:
        raw = pd.DataFrame(
            {
                "open_paisa": [10000],
                "high_paisa": [10500],
                "low_paisa": [9500],
                "close_paisa": [10200],
                "spot_paisa": [2360000],
                "strike_paisa": [2350000],
                "bar_time_ms": [1772409600000],  # 2026-03-02 00:00 UTC = 2026-03-02 05:30 IST
                "underlying": ["NIFTY"],
                "expiry_kind": ["WEEK"],
                "expiry_code": [1],
                "strike_offset": [-2],
                "option_type": ["CALL"],
                "interval_min": [5],
                "volume": [1000],
                "iv": [15.0],
                "oi": [5000],
                "ingested_at_ms": [1772409600000],
            }
        )
        out = convert_format(raw)
        ts = out["timestamp"].iloc[0]
        assert ts.tz is None  # naive
        assert ts == pd.Timestamp("2026-03-02 05:30")  # IST = UTC+5:30

    def test_symbol_construction(self) -> None:
        raw = pd.DataFrame(
            {
                "open_paisa": [10000],
                "high_paisa": [10500],
                "low_paisa": [9500],
                "close_paisa": [10200],
                "spot_paisa": [2360000],
                "strike_paisa": [2350000],
                "bar_time_ms": [1772496000000],
                "underlying": ["NIFTY"],
                "expiry_kind": ["WEEK"],
                "expiry_code": [1],
                "strike_offset": [-2],
                "option_type": ["CALL"],
                "interval_min": [5],
                "volume": [1000],
                "iv": [15.0],
                "oi": [5000],
                "ingested_at_ms": [1772496000000],
            }
        )
        out = convert_format(raw)
        assert out["symbol"].iloc[0] == "NIFTY_WEEK_1_-2_CALL"

    def test_exchange_set_to_nse(self) -> None:
        raw = pd.DataFrame(
            {
                "open_paisa": [10000],
                "high_paisa": [10500],
                "low_paisa": [9500],
                "close_paisa": [10200],
                "spot_paisa": [2360000],
                "strike_paisa": [2350000],
                "bar_time_ms": [1772496000000],
                "underlying": ["NIFTY"],
                "expiry_kind": ["WEEK"],
                "expiry_code": [1],
                "strike_offset": [-2],
                "option_type": ["CALL"],
                "interval_min": [5],
                "volume": [1000],
                "iv": [15.0],
                "oi": [5000],
                "ingested_at_ms": [1772496000000],
            }
        )
        out = convert_format(raw)
        assert (out["exchange"] == "NSE").all()

    def test_canonical_columns_complete(self) -> None:
        """All required columns for the option schema are listed."""
        required = {
            "timestamp",
            "symbol",
            "underlying",
            "exchange",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
            "iv",
            "spot",
            "strike",
            "strike_offset",
            "option_type",
            "expiry_kind",
            "expiry_code",
            "interval_min",
            "expiry_date",
        }
        assert required.issubset(set(CANONICAL_COLUMNS))


class TestConvertFromDhanRolling:
    def test_strike_mapping(self) -> None:
        assert strike_offset_to_dhan_strike(0) == "ATM"
        assert strike_offset_to_dhan_strike(2) == "ATM+2"
        assert strike_offset_to_dhan_strike(-3) == "ATM-3"

    def test_basic_conversion(self) -> None:
        side = {
            "timestamp": [1772496000],
            "open": [100.0],
            "high": [105.0],
            "low": [95.0],
            "close": [102.0],
            "volume": [1000],
            "oi": [5000],
            "iv": [15.0],
            "spot": [23600.0],
            "strike": [23500.0],
        }
        out = convert_from_dhan_rolling(
            side,
            underlying="NIFTY",
            expiry_kind="WEEK",
            expiry_code=1,
            strike_offset=-2,
            option_type="CALL",
            interval_min=5,
        )
        assert len(out) == 1
        assert out["symbol"].iloc[0] == "NIFTY_WEEK_1_-2_CALL"
        assert out["close"].iloc[0] == 102.0
        assert set(CANONICAL_COLUMNS).issubset(set(out.columns))


def _sample_options_df(ts: str, close: float = 102.0) -> pd.DataFrame:
    ts_val = pd.Timestamp(ts)
    return pd.DataFrame(
        [
            {
                "timestamp": ts_val,
                "symbol": "NIFTY_WEEK_1_-2_CALL",
                "underlying": "NIFTY",
                "exchange": "NSE",
                "open": close - 2.0,
                "high": close + 5.0,
                "low": close - 5.0,
                "close": close,
                "volume": 1000,
                "oi": 5000,
                "iv": 15.0,
                "spot": 23600.0,
                "strike": 23500.0,
                "strike_offset": -2,
                "option_type": "CALL",
                "expiry_kind": "WEEK",
                "expiry_code": 1,
                "interval_min": 5,
                "expiry_date": "2026-03-05",
            }
        ]
    )


def _setup_manifest(lake_root: Path) -> None:
    write_options_sync_manifest(
        str(lake_root),
        [OptionsSyncManifestEntry("NIFTY", "WEEK", 1)],
    )


class TestSyncOptions:
    def test_first_run_creates_files(self, tmp_path: Path) -> None:
        lake_root = tmp_path / "lake"
        tgt_path = tmp_path / "options"
        _setup_manifest(lake_root)

        summary = sync_options(
            lambda *a: _sample_options_df("2026-03-02 09:15:00"),
            target_root=tgt_path,
            lake_root=str(lake_root),
        )

        assert summary["files_created"] == 1
        assert summary["new_rows"] == 1
        assert (
            tgt_path / "underlying=NIFTY" / "expiry_kind=WEEK" / "expiry_code=1" / "data.parquet"
        ).exists()

    def test_written_file_uses_canonical_timestamp_unit(self, tmp_path: Path) -> None:
        lake_root = tmp_path / "lake"
        tgt_path = tmp_path / "options"
        _setup_manifest(lake_root)
        sync_options(
            lambda *a: _sample_options_df("2026-03-02 09:15:00"),
            target_root=tgt_path,
            lake_root=str(lake_root),
        )
        out_file = (
            tgt_path / "underlying=NIFTY" / "expiry_kind=WEEK" / "expiry_code=1" / "data.parquet"
        )
        assert pq.read_schema(out_file).field("timestamp").type == ARROW_SCHEMA.field(
            "timestamp"
        ).type

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        lake_root = tmp_path / "lake"
        tgt_path = tmp_path / "options"
        _setup_manifest(lake_root)
        calls = {"n": 0}

        def fetch_fn(*a):
            calls["n"] += 1
            return _sample_options_df("2026-03-02 09:15:00") if calls["n"] == 1 else pd.DataFrame(
                columns=CANONICAL_COLUMNS
            )

        sync_options(fetch_fn, target_root=tgt_path, lake_root=str(lake_root))
        s2 = sync_options(fetch_fn, target_root=tgt_path, lake_root=str(lake_root))
        assert s2["new_rows"] == 0

    def test_dedup_on_merge(self, tmp_path: Path) -> None:
        lake_root = tmp_path / "lake"
        tgt_path = tmp_path / "options"
        _setup_manifest(lake_root)
        calls = {"n": 0}

        def fetch_fn(*a):
            calls["n"] += 1
            return _sample_options_df(
                "2026-03-02 09:15:00", close=999.0 if calls["n"] > 1 else 100.0
            )

        sync_options(fetch_fn, target_root=tgt_path, lake_root=str(lake_root))
        sync_options(fetch_fn, target_root=tgt_path, lake_root=str(lake_root))
        df_out = pd.read_parquet(
            tgt_path / "underlying=NIFTY" / "expiry_kind=WEEK" / "expiry_code=1" / "data.parquet"
        )
        assert len(df_out) == 1
        assert df_out["close"].iloc[0] == 999.0

    def test_incremental_adds_new_rows(self, tmp_path: Path) -> None:
        lake_root = tmp_path / "lake"
        tgt_path = tmp_path / "options"
        _setup_manifest(lake_root)
        calls = {"n": 0}

        def fetch_fn(*a):
            calls["n"] += 1
            ts = "2026-03-02 09:15:00" if calls["n"] == 1 else "2026-03-02 09:30:00"
            return _sample_options_df(ts)

        sync_options(fetch_fn, target_root=tgt_path, lake_root=str(lake_root))
        s = sync_options(fetch_fn, target_root=tgt_path, lake_root=str(lake_root))
        assert s["new_rows"] == 1
        assert (
            len(
                pd.read_parquet(
                    tgt_path
                    / "underlying=NIFTY"
                    / "expiry_kind=WEEK"
                    / "expiry_code=1"
                    / "data.parquet"
                )
            )
            == 2
        )

    def test_watermark_none_when_no_file(self, tmp_path: Path) -> None:
        assert _get_watermark_date(tmp_path / "nope.parquet") is None

    def test_skips_when_up_to_date(self, tmp_path: Path) -> None:
        lake_root = tmp_path / "lake"
        tgt_path = tmp_path / "options"
        _setup_manifest(lake_root)
        today_df = _sample_options_df(f"{date.today()} 09:15:00")
        sync_options(lambda *a: today_df, target_root=tgt_path, lake_root=str(lake_root))
        s = sync_options(lambda *a: today_df, target_root=tgt_path, lake_root=str(lake_root))
        assert s["new_rows"] == 0
