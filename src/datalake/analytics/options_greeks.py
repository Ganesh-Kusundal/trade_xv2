"""Options Greeks precomputation — materialize BS Greeks per strike per timestamp.

Computes delta, gamma, theta, vega, rho for all option strikes using
Black-Scholes model and stores results as partitioned Parquet for
efficient point-in-time joins with underlying price data.

Usage:
    python -m datalake.options_greeks [--force]

    # Or programmatically:
    from datalake.options_greeks import OptionsGreeksPrecomputer
    pc = OptionsGreeksPrecomputer()
    pc.compute()
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from datalake.core.duckdb_utils import DEFAULT_CATALOG_PATH, get_pool

logger = logging.getLogger(__name__)

from domain.ports.data_catalog import DEFAULT_DATA_PATHS

GREEKS_ROOT = DEFAULT_DATA_PATHS.options_greeks_root


@dataclass
class OptionsGreeksPrecomputer:
    """Precompute and materialize Black-Scholes Greeks into partitioned Parquet."""

    catalog_path: str | Path = DEFAULT_CATALOG_PATH
    force: bool = False
    greeks_root: Path = GREEKS_ROOT
    risk_free_rate: float = 0.06
    lookback_days: int = 30

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        return get_pool().acquire(self.catalog_path, read_only=False)

    def _release_conn(self, conn) -> None:
        get_pool().release(self.catalog_path)

    def compute(self) -> Path:
        """Compute Greeks for all option data and write as partitioned Parquet."""
        if not self.force and self._greeks_exist():
            logger.info("Greeks already exist, skipping (use --force to re-compute)")
            return self.greeks_root

        conn = self._get_conn()
        try:
            sql = self._build_greeks_sql()
            self.greeks_root.mkdir(parents=True, exist_ok=True)

            copy_sql = f"""
                COPY ({sql}) TO '{self.greeks_root}/'
                (FORMAT PARQUET, PER_THREAD_OUTPUT TRUE,
                 PARTITION_BY (year, month),
                 ORDER BY (underlying, timestamp, strike, option_type))
            """
            conn.execute(copy_sql)
            logger.info("Wrote options Greeks to %s", self.greeks_root)
            return self.greeks_root
        finally:
            self._release_conn(conn)

    def _greeks_exist(self) -> bool:
        return self.greeks_root.exists() and list(self.greeks_root.rglob("*.parquet"))

    def _build_greeks_sql(self) -> str:
        """Build SQL that computes BS Greeks inline using DuckDB UDFs."""
        r = self.risk_free_rate
        return f"""
        WITH options AS (
            SELECT
                timestamp,
                underlying,
                strike,
                option_type,
                iv,
                ltp,
                spot,
                expiry_date,
                oi,
                volume,
                expiry_kind,
                expiry_code,
                EXTRACT(EPOCH FROM (CAST(expiry_date AS TIMESTAMP) - timestamp)) / 86400.0
                    AS days_to_expiry
            FROM read_parquet('market_data/options/chains/expiry=*/underlying=*/data.parquet')
            WHERE iv IS NOT NULL AND iv > 0
              AND spot IS NOT NULL AND spot > 0
              AND timestamp >= (SELECT MAX(timestamp) - INTERVAL '{self.lookback_days} days'
                                FROM read_parquet('market_data/options/chains/expiry=*/underlying=*/data.parquet'))
        ),
        with_t AS (
            SELECT *,
                GREATEST(days_to_expiry / 365.0, 1.0/365.0) AS t,
                {r} AS r
            FROM options
        ),
        with_d AS (
            SELECT *,
                (LN(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * SQRT(t)) AS d1,
                (LN(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * SQRT(t)) - iv * SQRT(t) AS d2
            FROM with_t
        ),
        with_norm AS (
            SELECT *,
                0.5 * (1.0 + ERF(d1 / SQRT(2))) AS norm_d1,
                0.5 * (1.0 + ERF(d2 / SQRT(2))) AS norm_d2,
                EXP(-0.5 * d1 * d1) / SQRT(2.0 * PI()) AS pdf_d1
            FROM with_d
        )
        SELECT
            timestamp,
            underlying,
            strike,
            option_type,
            iv,
            ltp,
            spot,
            expiry_date,
            oi,
            volume,
            days_to_expiry,
            -- Delta
            CASE
                WHEN option_type IN ('CE', 'CALL') THEN norm_d1
                ELSE norm_d1 - 1.0
            END AS delta,
            -- Gamma
            pdf_d1 / (spot * iv * SQRT(t)) AS gamma,
            -- Theta (per day)
            CASE
                WHEN option_type IN ('CE', 'CALL') THEN
                    (-(spot * pdf_d1 * iv) / (2.0 * SQRT(t))
                     - r * strike * EXP(-r * t) * norm_d2) / 365.0
                ELSE
                    (-(spot * pdf_d1 * iv) / (2.0 * SQRT(t))
                     + r * strike * EXP(-r * t) * (1.0 - norm_d2)) / 365.0
            END AS theta,
            -- Vega (per 1% move in IV)
            spot * pdf_d1 * SQRT(t) / 100.0 AS vega,
            -- Rho (per 1% move in rates)
            CASE
                WHEN option_type IN ('CE', 'CALL') THEN
                    strike * t * EXP(-r * t) * norm_d2 / 100.0
                ELSE
                    -strike * t * EXP(-r * t) * (1.0 - norm_d2) / 100.0
            END AS rho,
            YEAR(timestamp) AS year,
            MONTH(timestamp) AS month
        FROM with_norm
        WHERE delta IS NOT NULL
          AND gamma IS NOT NULL
          AND theta IS NOT NULL
          AND vega IS NOT NULL
        """

    def read_greeks(
        self,
        underlying: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Read precomputed Greeks from Parquet.

        Args:
            underlying: Filter by underlying symbol (e.g., "NIFTY").
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with precomputed Greeks.
        """
        glob_pattern = str(self.greeks_root / "year=*/month=*/*.parquet")
        conditions = []
        params = []

        if underlying:
            conditions.append("underlying = ?")
            params.append(underlying)
        if from_date:
            conditions.append("timestamp >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("timestamp <= ?")
            params.append(to_date)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT * FROM read_parquet('{glob_pattern}')
            {where}
            ORDER BY underlying, timestamp, strike, option_type
        """
        return duckdb.execute(query, params).fetchdf()


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Pre-compute options Greeks")
    parser.add_argument("--force", action="store_true", help="Re-compute even if exists")
    args = parser.parse_args()

    pc = OptionsGreeksPrecomputer(force=args.force)
    result = pc.compute()
    logger.info("Greeks written to: %s", result)


if __name__ == "__main__":
    main()
