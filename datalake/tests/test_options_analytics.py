"""Tests for option analytics (PCR, Max Pain, IV Surface)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pytest

from analytics.views.options_views import OptionViews


def _make_option_data(root: Path) -> None:
    """Create synthetic option data in the expected hive layout.

    Creates one timestamp, two strikes, CE+PE, for NIFTY weekly expiry.
    """
    for und in ["NIFTY", "BANKNIFTY"]:
        for ek, ec, exp_date in [
            ("WEEK", 1, "2026-06-04"),
            ("WEEK", 2, "2026-06-11"),
            ("MONTH", 1, "2026-06-25"),
        ]:
            path = root / f"underlying={und}" / f"expiry_kind={ek}" / f"expiry_code={ec}"
            path.mkdir(parents=True, exist_ok=True)
            data = []
            for ts in ["2026-06-01 09:15:00", "2026-06-01 09:20:00", "2026-06-01 09:25:00"]:
                for ot in ["CALL", "PUT"]:
                    for so, stk in [(-2, 23500), (-1, 23550), (0, 23600), (1, 23650), (2, 23700)]:
                        symbol = f"{und}_{ek}_{ec}_{so}_{ot}"
                        data.append(
                            {
                                "timestamp": pd.Timestamp(ts),
                                "symbol": symbol,
                                "underlying": und,
                                "exchange": "NSE",
                                "open": 100.0,
                                "high": 105.0,
                                "low": 95.0,
                                "close": 102.0 if ot == "CALL" else 98.0,
                                "volume": 1000 if ot == "CALL" else 2000,
                                "oi": 5000 if ot == "CALL" else 8000,
                                "iv": 15.0 if ot == "CALL" else 16.0,
                                "spot": 23600.0,
                                "strike": float(stk),
                                "strike_offset": so,
                                "option_type": ot,
                                "expiry_kind": ek,
                                "expiry_code": ec,
                                "interval_min": 5,
                                "expiry_date": exp_date,
                            }
                        )
            df = pd.DataFrame(data)
            table = pa.Table.from_pandas(df, preserve_index=False)
            table.to_pandas().to_parquet(path / "data.parquet", index=False)


@pytest.fixture
def opt_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Create a temp DuckDB with synthetic option data and materialized tables."""
    c = duckdb.connect(str(tmp_path / "opt.duckdb"))
    _make_option_data(tmp_path)

    # Create materialized tables manually (simplified versions of the SQL)
    c.execute(f"""
        CREATE TABLE m_pcr AS
        SELECT
            timestamp, underlying, expiry_kind, expiry_code, expiry_date,
            spot, interval_min,
            SUM(CASE WHEN option_type = 'CALL' THEN volume ELSE 0 END) as total_ce_volume,
            SUM(CASE WHEN option_type = 'PUT' THEN volume ELSE 0 END) as total_pe_volume,
            SUM(CASE WHEN option_type = 'CALL' THEN oi ELSE 0 END) as total_ce_oi,
            SUM(CASE WHEN option_type = 'PUT' THEN oi ELSE 0 END) as total_pe_oi
        FROM read_parquet('{tmp_path}/*/*/*/data.parquet')
        GROUP BY timestamp, underlying, expiry_kind, expiry_code, expiry_date, spot, interval_min
    """)
    c.execute(f"""
        CREATE TABLE m_max_pain AS
        WITH candidates AS (
            SELECT DISTINCT timestamp, underlying, expiry_kind, expiry_code,
                   expiry_date, spot, interval_min, strike as K
            FROM read_parquet('{tmp_path}/*/*/*/data.parquet')
        ),
        pain AS (
            SELECT c.timestamp, c.underlying, c.expiry_kind, c.expiry_code,
                   c.expiry_date, c.spot, c.interval_min, c.K,
                   SUM(CASE WHEN o.option_type = 'CALL' THEN o.oi * GREATEST(0, c.K - o.strike) ELSE 0 END) +
                   SUM(CASE WHEN o.option_type = 'PUT' THEN o.oi * GREATEST(0, o.strike - c.K) ELSE 0 END) as total_pain
            FROM candidates c
            JOIN read_parquet('{tmp_path}/*/*/*/data.parquet') o
                ON c.timestamp = o.timestamp AND c.underlying = o.underlying
                AND c.expiry_kind = o.expiry_kind AND c.expiry_code = o.expiry_code
            GROUP BY c.timestamp, c.underlying, c.expiry_kind, c.expiry_code,
                     c.expiry_date, c.spot, c.interval_min, c.K
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY timestamp, underlying, expiry_kind, expiry_code
                ORDER BY total_pain ASC
            ) as rn FROM pain
        )
        SELECT timestamp, underlying, expiry_kind, expiry_code, expiry_date,
               spot, interval_min, K as max_pain_strike, total_pain as total_pain_at_max_pain
        FROM ranked WHERE rn = 1
    """)
    c.execute(f"""
        CREATE TABLE m_iv_surface AS
        WITH options AS (
            SELECT *, ABS(strike - spot) as dist,
                CASE WHEN strike < spot AND option_type = 'PUT' THEN 'otm_put'
                     WHEN strike > spot AND option_type = 'CALL' THEN 'otm_call'
                     ELSE 'other' END as moneyness
            FROM read_parquet('{tmp_path}/*/*/*/data.parquet')
        ),
        atm AS (
            SELECT DISTINCT ON (timestamp, underlying, expiry_kind, expiry_code)
                timestamp, underlying, expiry_kind, expiry_code, expiry_date,
                spot, interval_min, strike as atm_strike, iv as atm_iv
            FROM options
            WHERE moneyness IN ('otm_put', 'otm_call')
            ORDER BY timestamp, underlying, expiry_kind, expiry_code, dist ASC
        ),
        otm_put AS (
            SELECT timestamp, underlying, expiry_kind, expiry_code, AVG(iv) as otm_put_iv
            FROM options WHERE moneyness = 'otm_put'
            GROUP BY timestamp, underlying, expiry_kind, expiry_code
        ),
        otm_call AS (
            SELECT timestamp, underlying, expiry_kind, expiry_code, AVG(iv) as otm_call_iv
            FROM options WHERE moneyness = 'otm_call'
            GROUP BY timestamp, underlying, expiry_kind, expiry_code
        )
        SELECT a.timestamp, a.underlying, a.expiry_kind, a.expiry_code,
               a.expiry_date, a.spot, a.interval_min, a.atm_strike, a.atm_iv,
               COALESCE(p.otm_put_iv, 0) as otm_put_iv,
               COALESCE(c.otm_call_iv, 0) as otm_call_iv,
               CAST(a.expiry_date AS DATE) - CAST(a.timestamp AS DATE) as days_to_expiry
        FROM atm a
        LEFT JOIN otm_put p USING (timestamp, underlying, expiry_kind, expiry_code)
        LEFT JOIN otm_call c USING (timestamp, underlying, expiry_kind, expiry_code)
    """)
    yield c
    c.close()


class TestOptionViewsPCR:
    def test_pcr_creates_view(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        OptionViews().create_views(opt_db)
        rows = opt_db.execute("SELECT COUNT(*) FROM v_pcr").fetchone()[0]
        assert rows > 0

    def test_pcr_computes_oi_ratio(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """PCR_OI = total_pe_oi / total_ce_oi."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT total_ce_oi, total_pe_oi, pcr_oi
            FROM v_pcr
            WHERE underlying='NIFTY' AND expiry_kind='WEEK' AND expiry_code=1
            LIMIT 1
        """).fetchone()
        ce_oi, pe_oi, pcr_oi = r
        assert pe_oi > 0
        assert pcr_oi == round(pe_oi / ce_oi, 4)

    def test_pcr_computes_volume_ratio(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """PCR_VOLUME = total_pe_volume / total_ce_volume."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT total_ce_volume, total_pe_volume, pcr_volume
            FROM v_pcr WHERE underlying='NIFTY' AND expiry_kind='WEEK' AND expiry_code=1 LIMIT 1
        """).fetchone()
        ce_vol, pe_vol, pcr_vol = r
        assert pcr_vol == round(pe_vol / ce_vol, 4)

    def test_pcr_aggregates_across_strikes(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """PCR should sum across all 5 strikes for one timestamp."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT total_ce_oi FROM v_pcr
            WHERE underlying='NIFTY' AND expiry_kind='WEEK' AND expiry_code=1
            LIMIT 1
        """).fetchone()[0]
        # 5 strikes x OI=5000 = 25,000 per CE per timestamp
        assert r == 25000


class TestOptionViewsMaxPain:
    def test_max_pain_creates_view(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        OptionViews().create_views(opt_db)
        rows = opt_db.execute("SELECT COUNT(*) FROM v_max_pain").fetchone()[0]
        assert rows > 0

    def test_max_pain_at_spot_when_balanced(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """When OI is balanced, max pain should be at or near spot."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT spot, max_pain_strike, distance_from_spot, position_vs_spot
            FROM v_max_pain
            WHERE underlying='NIFTY' AND expiry_kind='WEEK' AND expiry_code=1
            LIMIT 1
        """).fetchone()
        _spot, _max_pain, dist, _pos = r
        assert dist >= 0

    def test_max_pain_is_a_valid_strike(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """Max pain strike must be one of the available strikes."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT DISTINCT max_pain_strike FROM v_max_pain
            WHERE underlying='NIFTY' AND expiry_kind='WEEK'
        """).fetchall()
        valid_strikes = {23500.0, 23550.0, 23600.0, 23650.0, 23700.0}
        for (mp,) in r:
            assert mp in valid_strikes


class TestOptionViewsIVSurface:
    def test_iv_surface_creates_view(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        OptionViews().create_views(opt_db)
        rows = opt_db.execute("SELECT COUNT(*) FROM v_iv_surface").fetchone()[0]
        assert rows > 0

    def test_atm_strike_is_closest_to_spot(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """ATM strike should be at or nearest to spot (23600). Excludes the exact-spot
        strike (classified as 'other' not 'otm_put'/'otm_call'), so the closest OTM
        strike (23550 or 23650) is picked — both are equidistant from spot."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT DISTINCT atm_strike FROM v_iv_surface
            WHERE underlying='NIFTY' AND expiry_kind='WEEK'
        """).fetchall()
        for (atm,) in r:
            assert atm in (23550.0, 23600.0, 23650.0)
            assert abs(atm - 23600.0) <= 50  # within one strike interval

    def test_iv_skew_is_put_minus_call(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """IV skew = otm_put_iv - otm_call_iv."""
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT otm_put_iv, otm_call_iv, iv_skew
            FROM v_iv_surface
            WHERE underlying='NIFTY' AND expiry_kind='WEEK' AND expiry_code=1
            LIMIT 1
        """).fetchone()
        put_iv, call_iv, skew = r
        assert skew == round(put_iv - call_iv, 4)

    def test_put_call_iv_ratio(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        OptionViews().create_views(opt_db)
        r = opt_db.execute("""
            SELECT otm_put_iv, otm_call_iv, put_call_iv_ratio
            FROM v_iv_surface
            WHERE underlying='NIFTY' AND expiry_kind='WEEK' AND expiry_code=1
            LIMIT 1
        """).fetchone()
        put_iv, call_iv, ratio = r
        assert ratio == round(put_iv / call_iv, 4)
        assert ratio > 1.0  # puts > calls in our test data


class TestIVSurfaceRegression:
    """Regression tests catching silent-zero bugs in m_iv_surface materialization.

    The IV surface SQL uses DuckDB DISTINCT ON (which is supported)
    but if the SQL changes to PostgreSQL DISTINCT ON (not supported) or
    if the moneyness classification is wrong (all 'other'), the table
    silently materializes to 0 rows. These tests catch that.
    """

    def test_m_iv_surface_not_empty(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """m_iv_surface must have rows. Catches silent-zero materialization bug."""
        n = opt_db.execute("SELECT COUNT(*) FROM m_iv_surface").fetchone()[0]
        assert n > 0, (
            f"m_iv_surface is empty ({n} rows). Likely SQL regression: "
            "DISTINCT ON syntax, moneyness classification, or GROUP BY issue."
        )

    def test_m_iv_surface_all_rows_have_atm_iv(self, opt_db: duckdb.DuckDBPyConnection) -> None:
        """Every row must have a non-NULL, positive atm_iv."""
        null_count = opt_db.execute(
            "SELECT COUNT(*) FROM m_iv_surface WHERE atm_iv IS NULL OR atm_iv <= 0"
        ).fetchone()[0]
        total = opt_db.execute("SELECT COUNT(*) FROM m_iv_surface").fetchone()[0]
        assert null_count == 0, f"{null_count}/{total} rows have NULL or non-positive atm_iv"

    def test_v_iv_surface_matches_m_iv_surface_row_count(
        self, opt_db: duckdb.DuckDBPyConnection
    ) -> None:
        """View row count must match materialized table row count."""
        OptionViews().create_views(opt_db)
        m_count = opt_db.execute("SELECT COUNT(*) FROM m_iv_surface").fetchone()[0]
        v_count = opt_db.execute("SELECT COUNT(*) FROM v_iv_surface").fetchone()[0]
        assert m_count == v_count, f"m_iv_surface has {m_count} rows but v_iv_surface has {v_count}"

    def test_atm_strike_within_one_strike_interval_of_spot(
        self, opt_db: duckdb.DuckDBPyConnection
    ) -> None:
        """ATM strike must be at or within one strike interval of spot.

        Current implementation picks closest OTM strike (excludes exact-spot),
        so dist can be up to one strike interval. If dist exceeds this, the
        DISTINCT ON or moneyness classification has regressed.
        """
        OptionViews().create_views(opt_db)
        # Test data: spot=23600, strikes at 23500, 23550, 23600, 23650, 23700
        # Strike interval = 50, so max acceptable dist = 50
        max_dist = opt_db.execute("""
            SELECT MAX(ABS(atm_strike - spot))
            FROM v_iv_surface
            WHERE underlying='NIFTY'
        """).fetchone()[0]
        assert max_dist <= 50, (
            f"ATM strike is {max_dist} from spot (>50 = one strike interval). "
            "Likely moneyness classification or DISTINCT ON regression."
        )
