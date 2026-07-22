"""DuckDB views over contract-centric lake layout (ADR-0023)."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from domain.ports.data_catalog import DEFAULT_DATA_PATHS

logger = logging.getLogger(__name__)


class ContractViews:
    """Contract-centric read views; rolling research views derived at query time."""

    def __init__(self, lake_root: str | None = None) -> None:
        self._root = Path(lake_root or DEFAULT_DATA_PATHS.lake_root)

    def create_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        root = str(self._root).replace("'", "''")
        opt_glob = f"{root}/contracts/options/candles/**/data.parquet"
        fut_glob = f"{root}/contracts/futures/candles/**/data.parquet"
        import glob as _glob

        if _glob.glob(f"{self._root}/contracts/options/candles/**/data.parquet", recursive=True):
            conn.execute(f"""
                CREATE OR REPLACE VIEW v_contract_options AS
                SELECT * FROM read_parquet('{opt_glob}', union_by_name=true)
            """)
        else:
            conn.execute("""
                CREATE OR REPLACE VIEW v_contract_options AS
                SELECT CAST(NULL AS TIMESTAMP) AS timestamp WHERE 1=0
            """)
        if _glob.glob(f"{self._root}/contracts/futures/candles/**/data.parquet", recursive=True):
            conn.execute(f"""
                CREATE OR REPLACE VIEW v_contract_futures AS
                SELECT * FROM read_parquet('{fut_glob}', union_by_name=true)
            """)
        else:
            conn.execute("""
                CREATE OR REPLACE VIEW v_contract_futures AS
                SELECT CAST(NULL AS TIMESTAMP) AS timestamp WHERE 1=0
            """)
        conn.execute("""
            CREATE OR REPLACE VIEW v_rolling_options_derived AS
            SELECT * FROM v_contract_options
            WHERE expiry_date = (
                SELECT MAX(expiry_date)
                FROM v_contract_options vo2
                WHERE vo2.underlying = v_contract_options.underlying
                  AND vo2.exchange = v_contract_options.exchange
            )
        """)
        logger.debug("Created contract-centric DuckDB views")
