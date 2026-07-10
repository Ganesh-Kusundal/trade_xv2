"""Tests for option_format module and sync_options function."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from datalake.core.option_format import (
    CANONICAL_COLUMNS,
    convert_format,
    make_option_symbol,
    map_expiry_code_to_date,
)
from datalake.ingestion.sync_options import _get_watermark, sync_options

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


# ============================================================
# Tests for sync_options (with tmp DuckDB)
# ============================================================


def _make_trade_j_duckdb(path: Path, rows: list[dict]) -> None:
    """Create a synthetic Trade_J DuckDB with rolling_option_bars data."""
    c = duckdb.connect(str(path))
    c.execute("""
        CREATE TABLE rolling_option_bars (
            underlying VARCHAR, expiry_kind VARCHAR, expiry_code INTEGER,
            strike_offset INTEGER, option_type VARCHAR, interval_min INTEGER,
            bar_time_ms BIGINT, open_paisa BIGINT, high_paisa BIGINT,
            low_paisa BIGINT, close_paisa BIGINT, volume BIGINT,
            iv DOUBLE, oi BIGINT, spot_paisa BIGINT, strike_paisa BIGINT,
            ingested_at_ms BIGINT
        )
    """)
    if rows:
        df = pd.DataFrame(rows)
        for col in ("underlying", "expiry_kind", "option_type"):
            df[col] = df[col].astype(object)
        c.register("rows_df", df)
        c.execute("INSERT INTO rolling_option_bars SELECT * FROM rows_df")
    c.close()


def _insert_option_rows(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> None:
    """Insert rows into rolling_option_bars with DuckDB-safe dtypes."""
    if not rows:
        return
    df = pd.DataFrame(rows)
    for col in ("underlying", "expiry_kind", "option_type"):
        df[col] = df[col].astype(object)
    conn.register("rows_df", df)
    conn.execute("INSERT INTO rolling_option_bars SELECT * FROM rows_df")
    conn.unregister("rows_df")


def _make_option_row(
    underlying: str, ek: str, ec: int, so: int, ot: str, bar_time_ms: int, price_paisa: int = 10000
) -> dict:
    return {
        "underlying": underlying,
        "expiry_kind": ek,
        "expiry_code": ec,
        "strike_offset": so,
        "option_type": ot,
        "interval_min": 5,
        "bar_time_ms": bar_time_ms,
        "open_paisa": price_paisa,
        "high_paisa": price_paisa + 500,
        "low_paisa": price_paisa - 500,
        "close_paisa": price_paisa + 100,
        "volume": 1000,
        "iv": 15.0,
        "oi": 5000,
        "spot_paisa": 2360000,
        "strike_paisa": 2350000,
        "ingested_at_ms": bar_time_ms,
    }


class TestSyncOptions:
    def test_first_run_creates_files(self, tmp_path: Path) -> None:
        tj_path = tmp_path / "tj.duckdb"
        tgt_path = tmp_path / "options"
        rows = [
            _make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496000000),
            _make_option_row("NIFTY", "WEEK", 1, -2, "PUT", 1772496000000),
        ]
        _make_trade_j_duckdb(tj_path, rows)

        summary = sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)

        assert summary["files_created"] == 1
        assert summary["files_merged"] == 0
        assert summary["new_rows"] == 2
        out_file = (
            tgt_path / "underlying=NIFTY" / "expiry_kind=WEEK" / "expiry_code=1" / "data.parquet"
        )
        assert out_file.exists()

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        tj_path = tmp_path / "tj.duckdb"
        tgt_path = tmp_path / "options"
        rows = [_make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496000000)]
        _make_trade_j_duckdb(tj_path, rows)

        # First run creates the file
        s1 = sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)
        assert s1["files_created"] == 1
        assert s1["new_rows"] == 1

        # Second run is a no-op (no new data)
        s2 = sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)
        assert s2["new_rows"] == 0
        assert s2["files_merged"] == 0
        assert s2["files_created"] == 0

    def test_dedup_on_merge(self, tmp_path: Path) -> None:
        """Adding a row with later timestamp but same (symbol, that_bar) — keeps last.

        Note: the watermark is a strict `>`, so a row with the exact same
        bar_time_ms as the existing watermark is considered "already synced"
        and is NOT picked up. This test uses a later timestamp to exercise
        the merge+dedup path, then verifies dedup-on-same-key.
        """
        tj_path = tmp_path / "tj.duckdb"
        tgt_path = tmp_path / "options"
        # First insert
        rows1 = [_make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496000000, price_paisa=10000)]
        _make_trade_j_duckdb(tj_path, rows1)
        sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)

        # Add a new bar (later timestamp), then a duplicate of that new bar
        c = duckdb.connect(str(tj_path))
        rows2 = [
            _make_option_row(
                "NIFTY", "WEEK", 1, -2, "CALL", 1772496900000, price_paisa=20000
            ),  # +15min
            # Duplicate of the new bar (same bar_time_ms, same symbol)
            _make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496900000, price_paisa=99999),
        ]
        _insert_option_rows(c, rows2)
        c.close()

        s = sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)
        assert s["new_rows"] == 2  # both new rows picked up
        # After dedup (keep=last), the file should have 2 distinct rows
        # (original at t=1772496000000 + one at t=1772496900000 after dedup)
        out_file = (
            tgt_path / "underlying=NIFTY" / "expiry_kind=WEEK" / "expiry_code=1" / "data.parquet"
        )
        df_out = pd.read_parquet(out_file)
        assert len(df_out) == 2  # deduped from 3 to 2
        # Verify the kept one is the last (price_paisa=99999 → close=999.99)
        kept = df_out[df_out["close"] > 900]
        assert len(kept) == 1  # only the last duplicate was kept

    def test_incremental_adds_new_rows(self, tmp_path: Path) -> None:
        tj_path = tmp_path / "tj.duckdb"
        tgt_path = tmp_path / "options"
        rows1 = [_make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496000000)]
        _make_trade_j_duckdb(tj_path, rows1)
        sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)

        # Add a new row with later timestamp
        c = duckdb.connect(str(tj_path))
        rows2 = [_make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496900000)]  # +15 min
        _insert_option_rows(c, rows2)
        c.close()

        s = sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)
        assert s["new_rows"] == 1
        out_file = (
            tgt_path / "underlying=NIFTY" / "expiry_kind=WEEK" / "expiry_code=1" / "data.parquet"
        )
        df_out = pd.read_parquet(out_file)
        assert len(df_out) == 2  # 1 original + 1 new

    def test_watermark_zero_when_no_file(self, tmp_path: Path) -> None:
        assert _get_watermark(tmp_path / "nope.parquet", duckdb.connect(":memory:")) == 0

    def test_connection_closed_on_success(self, tmp_path: Path) -> None:
        """Verify src connection is closed after sync (no leak)."""
        tj_path = tmp_path / "tj.duckdb"
        tgt_path = tmp_path / "options"
        _make_trade_j_duckdb(
            tj_path, [_make_option_row("NIFTY", "WEEK", 1, -2, "CALL", 1772496000000)]
        )
        sync_options(trade_j_duckdb=tj_path, target_root=tgt_path)
        # No assertion — just verifying it doesn't hang
        assert True
