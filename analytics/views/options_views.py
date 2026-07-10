"""Layer 7: Option Analytics — PCR, Max Pain, IV Surface.

Reads from migrated option Parquet data in market_data/options/candles/.
All views read from materialized tables (m_pcr, m_max_pain, m_iv_surface) for speed.
"""

from __future__ import annotations

import logging

import duckdb

from datalake.analytics.options_analytics_sql import SQL_M_IV_SURFACE, SQL_M_MAX_PAIN, SQL_M_PCR

logger = logging.getLogger(__name__)


class OptionViews:
    """Creates option analytics views in DuckDB."""

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create all option analytics views.

        Expects m_pcr, m_max_pain, m_iv_surface to already be materialized
        (see OptionViews.materialization_sql).
        """
        self._create_pcr(conn)
        self._create_max_pain(conn)
        self._create_iv_surface(conn)

    @staticmethod
    def materialization_sql() -> list[tuple[str, str]]:
        """SQL for option analytics tables (PCR, Max Pain, IV surface)."""
        return [
            ("m_pcr", SQL_M_PCR),
            ("m_max_pain", SQL_M_MAX_PAIN),
            ("m_iv_surface", SQL_M_IV_SURFACE),
        ]

    def _create_pcr(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_pcr — Put-Call Ratio (volume + OI) per (timestamp, underlying, expiry)."""
        conn.execute("""
            CREATE OR REPLACE VIEW v_pcr AS
            SELECT
                timestamp,
                underlying,
                expiry_kind,
                expiry_code,
                expiry_date,
                spot,
                total_ce_volume,
                total_pe_volume,
                total_ce_oi,
                total_pe_oi,
                CASE WHEN total_ce_volume > 0
                     THEN ROUND(total_pe_volume * 1.0 / total_ce_volume, 4)
                     ELSE NULL END as pcr_volume,
                CASE WHEN total_ce_oi > 0
                     THEN ROUND(total_pe_oi * 1.0 / total_ce_oi, 4)
                     ELSE NULL END as pcr_oi
            FROM m_pcr
            ORDER BY timestamp, underlying, expiry_kind, expiry_code
        """)
        logger.debug("Created v_pcr")

    def _create_max_pain(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_max_pain — Max Pain strike per (timestamp, underlying, expiry).

        Max pain = strike that minimizes the total option holder loss.
        For each candidate strike K, total pain = sum over all strikes S of:
          CE_oi(S) * max(0, K - S) + PE_oi(S) * max(0, S - K)
        """
        conn.execute("""
            CREATE OR REPLACE VIEW v_max_pain AS
            SELECT
                timestamp,
                underlying,
                expiry_kind,
                expiry_code,
                expiry_date,
                spot,
                max_pain_strike,
                total_pain_at_max_pain,
                ROUND(ABS(spot - max_pain_strike), 2) as distance_from_spot,
                CASE
                    WHEN max_pain_strike < spot THEN 'below_spot'
                    WHEN max_pain_strike > spot THEN 'above_spot'
                    ELSE 'at_spot'
                END as position_vs_spot
            FROM m_max_pain
            ORDER BY timestamp, underlying, expiry_kind, expiry_code
        """)
        logger.debug("Created v_max_pain")

    def _create_iv_surface(self, conn: duckdb.DuckDBPyConnection) -> None:
        """v_iv_surface — IV term structure + skew per (timestamp, underlying, expiry).

        ATM IV = IV at the strike closest to spot.
        IV skew = OTM put IV (5 strikes OTM) - OTM call IV (5 strikes OTM).
        days_to_expiry is computed per-bar from the rolling expiry_code:
        - WEEK: nearest Thursday on or after timestamp (code=1) or +7 days (code=2)
        - MONTH: last Thursday of the month containing timestamp
        """
        conn.execute("""
            CREATE OR REPLACE VIEW v_iv_surface AS
            SELECT
                timestamp,
                underlying,
                expiry_kind,
                expiry_code,
                expiry_date,
                spot,
                atm_strike,
                atm_iv,
                otm_put_iv,
                otm_call_iv,
                ROUND(otm_put_iv - otm_call_iv, 4) as iv_skew,
                CASE
                    WHEN otm_call_iv > 0 THEN ROUND(otm_put_iv / otm_call_iv, 4)
                    ELSE NULL
                END as put_call_iv_ratio,
                -- Per-bar days_to_expiry: actual expiry date computed from rolling code
                CASE
                    WHEN expiry_kind = 'WEEK' THEN
                        CAST(CAST(timestamp AS DATE) +
                            INTERVAL ((4 - date_part('dow', CAST(timestamp AS DATE)) + 7) % 7) DAY +
                            INTERVAL ((expiry_code - 1) * 7) DAY
                        AS DATE) - CAST(timestamp AS DATE)
                    WHEN expiry_kind = 'MONTH' THEN
                        CAST(DATE_TRUNC('month', CAST(timestamp AS DATE)) +
                            INTERVAL '1 month' - INTERVAL '1 day' -
                            INTERVAL ((date_part('dow', DATE_TRUNC('month', CAST(timestamp AS DATE)) +
                                INTERVAL '1 month' - INTERVAL '1 day') - 4 + 7) % 7) DAY
                        AS DATE) -
                        CAST(timestamp AS DATE)
                    ELSE days_to_expiry
                END as days_to_expiry
            FROM m_iv_surface
            ORDER BY timestamp, underlying, expiry_kind, expiry_code
        """)
        logger.debug("Created v_iv_surface")
