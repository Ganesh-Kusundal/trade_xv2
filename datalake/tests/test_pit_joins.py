from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest

from datalake.core.pit_joins import (
    as_of_join,
    pit_query,
    validate_no_lookahead,
)


def _make_temporal_table(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    symbols: list[str] | None = None,
) -> None:
    if symbols is None:
        symbols = ["RELIANCE"]
    np.random.seed(42)
    rows = []
    for sym in symbols:
        for i in range(50):
            ts = pd.Timestamp("2026-01-01 09:15:00") + pd.Timedelta(minutes=i)
            published = ts + pd.Timedelta(seconds=1)
            rows.append(
                f"(TIMESTAMP '{ts}', '{sym}', 100.0, 105.0, 99.0, 101.0, 1000, 0, TIMESTAMP '{ts}', TIMESTAMP '{published}')"
            )
    data_sql = ",".join(rows)
    conn.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT * FROM (VALUES {data_sql})
        AS t(timestamp, symbol, open, high, low, close, volume, oi, event_time, published_at)
    """)


class TestAsOfJoin:
    def test_basic_asof_join(self) -> None:
        conn = duckdb.connect()
        try:
            _make_temporal_table(conn, "candles")
            conn.execute("""
                CREATE OR REPLACE TABLE features AS
                SELECT * FROM (VALUES
                    (TIMESTAMP '2026-01-01 09:15:00', 'RELIANCE', 14.5, 55.0,
                     TIMESTAMP '2026-01-01 09:15:00', FALSE)
                ) AS t(event_time, symbol, atr_14, rsi_14, published_at, is_correction)
            """)
            df = as_of_join(
                conn=conn,
                left_table="candles",
                right_table="features",
                on=["symbol"],
                select_left=["event_time", "symbol", "close"],
                select_right=["atr_14", "rsi_14"],
            )
            assert not df.empty
            assert "atr_14" in df.columns
            assert "rsi_14" in df.columns
            assert len(df) == 50
        finally:
            conn.close()

    def test_raises_on_missing_columns(self) -> None:
        conn = duckdb.connect()
        try:
            conn.execute("""
                CREATE OR REPLACE TABLE bad_left AS
                SELECT 1 AS id, 'A' AS name
            """)
            conn.execute("""
                CREATE OR REPLACE TABLE bad_right AS
                SELECT 1 AS id, 10.0 AS val
            """)
            with pytest.raises(ValueError, match="missing required temporal"):
                as_of_join(
                    conn=conn,
                    left_table="bad_left",
                    right_table="bad_right",
                    on=["id"],
                )
        finally:
            conn.close()

    def test_empty_right_table(self) -> None:
        conn = duckdb.connect()
        try:
            _make_temporal_table(conn, "candles")
            conn.execute("""
                CREATE OR REPLACE TABLE empty_features AS
                SELECT * FROM (VALUES
                    (TIMESTAMP '2020-01-01', 'NONEXISTENT', 0.0, 0.0,
                     TIMESTAMP '2020-01-01', FALSE)
                ) AS t(event_time, symbol, atr_14, rsi_14, published_at, is_correction)
                WHERE 1=0
            """)
            df = as_of_join(
                conn=conn,
                left_table="candles",
                right_table="empty_features",
                on=["symbol"],
                select_left=["event_time", "symbol", "close"],
                select_right=["atr_14"],
            )
            assert df.empty
        finally:
            conn.close()

    def test_with_config_max_lookback(self) -> None:
        conn = duckdb.connect()
        try:
            conn.execute("""
                CREATE OR REPLACE TABLE l AS
                SELECT * FROM (VALUES
                    (TIMESTAMP '2026-01-01 09:15:00', 'A', 100.0,
                     TIMESTAMP '2026-01-01 09:15:00', TIMESTAMP '2026-01-01 09:15:01'),
                    (TIMESTAMP '2026-01-02 09:15:00', 'A', 101.0,
                     TIMESTAMP '2026-01-02 09:15:00', TIMESTAMP '2026-01-02 09:15:01')
                ) AS t(event_time, symbol, close, event_time_2, published_at)
            """)
            conn.execute("""
                CREATE OR REPLACE TABLE r AS
                SELECT * FROM (VALUES
                    (TIMESTAMP '2026-01-01 09:15:00', 'A', 14.0,
                     TIMESTAMP '2026-01-01 09:15:00', TIMESTAMP '2026-01-01 09:15:01'),
                    (TIMESTAMP '2025-12-01 09:15:00', 'A', 12.0,
                     TIMESTAMP '2025-12-01 09:15:00', TIMESTAMP '2025-12-01 09:15:01')
                ) AS t(event_time, symbol, atr_14, event_time_2, published_at)
            """)
            from datalake.core.pit_joins import PitQueryConfig

            config = PitQueryConfig(max_lookback_window="INTERVAL 30 DAYS")
            df = as_of_join(
                conn=conn,
                left_table="l",
                right_table="r",
                on=["symbol"],
                config=config,
                select_left=["event_time", "symbol"],
                select_right=["atr_14"],
            )
            assert not df.empty
        finally:
            conn.close()


class TestPitQuery:
    def test_substitutes_placeholder(self) -> None:
        conn = duckdb.connect()
        try:
            conn.execute("""
                CREATE OR REPLACE TABLE test_data AS
                SELECT * FROM (VALUES
                    (TIMESTAMP '2026-01-01 09:15:00', 100.0),
                    (TIMESTAMP '2026-01-02 09:15:00', 101.0)
                ) AS t(event_time, close)
            """)
            df = pit_query(
                conn,
                "SELECT * FROM test_data WHERE event_time <= {as_of_time}",
                as_of_time="2026-01-01 23:59:59",
            )
            assert len(df) == 1
        finally:
            conn.close()

    def test_strict_mode_rejects_lookahead(self) -> None:
        conn = duckdb.connect()
        try:
            conn.execute("CREATE OR REPLACE TABLE t AS SELECT 1 AS x")
            from datalake.core.pit_joins import PitQueryConfig

            config = PitQueryConfig(strict=True)
            with pytest.raises(ValueError, match="Look-ahead"):
                pit_query(
                    conn,
                    "SELECT LEAD(x) OVER () FROM t WHERE x <= {as_of_time}",
                    as_of_time="2026-01-01",
                    config=config,
                )
        finally:
            conn.close()


class TestValidateNoLookahead:
    def test_detects_lead(self) -> None:
        warnings = validate_no_lookahead("SELECT LEAD(close) OVER () FROM t")
        assert len(warnings) == 1
        assert "LEAD" in warnings[0]

    def test_detects_unbounded_following(self) -> None:
        warnings = validate_no_lookahead(
            "SELECT SUM(x) OVER (ROWS BETWEEN 1 PRECEDING AND UNBOUNDED FOLLOWING) FROM t"
        )
        assert any("UNBOUNDED FOLLOWING" in w for w in warnings)

    def test_detects_rows_following(self) -> None:
        warnings = validate_no_lookahead(
            "SELECT SUM(x) OVER (ROWS BETWEEN 1 PRECEDING AND 2 FOLLOWING) FROM t"
        )
        assert len(warnings) >= 1

    def test_passes_clean_sql(self) -> None:
        warnings = validate_no_lookahead("SELECT close, LAG(close) OVER () FROM t")
        assert len(warnings) == 0

    def test_multiple_lead_calls(self) -> None:
        sql = "SELECT LEAD(x) OVER (), LEAD(y) OVER () FROM t"
        warnings = validate_no_lookahead(sql)
        assert len(warnings) >= 1

    def test_no_false_positive_on_lag(self) -> None:
        warnings = validate_no_lookahead("SELECT LAG(close, 1) OVER () FROM t")
        assert len(warnings) == 0
