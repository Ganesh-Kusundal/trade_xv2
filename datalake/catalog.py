"""DuckDB Catalog — metadata store for the data lake.

Tracks: symbols, date ranges, row counts, data quality, missing data.
Provides fast queries over Parquet files without loading them.

Connections are thread-local so concurrent scanners / strategies can safely
read and write without sharing a single DuckDB connection object.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from datetime import datetime, date

import duckdb

logger = logging.getLogger(__name__)


class DataCatalog:
    """DuckDB-backed metadata catalog for the data lake."""

    def __init__(self, root: str = "market_data", read_only: bool = False) -> None:
        self._root = Path(root)
        self._db_path = self._root / "catalog.duckdb"
        self._read_only = read_only
        self._conns: dict[int, duckdb.DuckDBPyConnection] = {}
        self._lock = threading.RLock()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        tid = threading.current_thread().ident
        if tid is None:
            tid = 0
        with self._lock:
            conn = self._conns.get(tid)
            if conn is None:
                if not self._read_only:
                    self._db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = duckdb.connect(str(self._db_path), read_only=self._read_only)
                if not self._read_only:
                    self._init_schema(conn)
                self._conns[tid] = conn
            return conn

    def close(self) -> None:
        with self._lock:
            for conn in list(self._conns.values()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._conns.clear()

    def _init_schema(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create catalog tables if they don't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                symbol VARCHAR PRIMARY KEY,
                exchange VARCHAR DEFAULT 'NSE',
                instrument_type VARCHAR DEFAULT 'EQUITY',
                sector VARCHAR DEFAULT '',
                isin VARCHAR DEFAULT '',
                lot_size INTEGER DEFAULT 1,
                tick_size DOUBLE DEFAULT 0.05,
                first_date DATE,
                last_date DATE,
                total_rows BIGINT DEFAULT 0,
                timeframe VARCHAR DEFAULT '1m',
                parquet_path VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_quality (
                symbol VARCHAR,
                check_date DATE,
                timeframe VARCHAR DEFAULT '1m',
                total_rows BIGINT DEFAULT 0,
                missing_candles INTEGER DEFAULT 0,
                duplicate_candles INTEGER DEFAULT 0,
                gap_days INTEGER DEFAULT 0,
                min_date DATE,
                max_date DATE,
                completeness_pct DOUBLE DEFAULT 0.0,
                status VARCHAR DEFAULT 'UNKNOWN',
                details VARCHAR DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, check_date, timeframe)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS download_jobs (
                job_id INTEGER PRIMARY KEY,
                universe VARCHAR,
                timeframe VARCHAR,
                symbols_total INTEGER DEFAULT 0,
                symbols_completed INTEGER DEFAULT 0,
                symbols_failed INTEGER DEFAULT 0,
                status VARCHAR DEFAULT 'PENDING',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message VARCHAR DEFAULT ''
            )
        """)

    def register_symbol(
        self,
        symbol: str,
        exchange: str = "NSE",
        first_date: date | None = None,
        last_date: date | None = None,
        total_rows: int = 0,
        timeframe: str = "1m",
        parquet_path: str = "",
        **kwargs,
    ) -> None:
        """Register or update a symbol in the catalog."""
        self.conn.execute("""
            INSERT OR REPLACE INTO symbols
            (symbol, exchange, first_date, last_date, total_rows, timeframe, parquet_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [symbol, exchange, first_date, last_date, total_rows, timeframe, parquet_path])

    def get_symbol(self, symbol: str) -> dict | None:
        """Get symbol metadata."""
        result = self.conn.execute(
            "SELECT * FROM symbols WHERE symbol = ?", [symbol]
        ).fetchone()
        if result is None:
            return None
        cols = [desc[0] for desc in self.conn.description]
        return dict(zip(cols, result))

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all registered symbols."""
        results = self.conn.execute(
            "SELECT symbol FROM symbols WHERE timeframe = ? ORDER BY symbol",
            [timeframe],
        ).fetchall()
        return [r[0] for r in results]

    def get_parquet_path(self, symbol: str, timeframe: str = "1m") -> Path | None:
        """Get the Parquet file path for a symbol."""
        row = self.conn.execute(
            "SELECT parquet_path FROM symbols WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe],
        ).fetchone()
        if row and row[0]:
            return Path(row[0])
        return None

    def scan_parquet_files(self, timeframe: str = "1m") -> int:
        """Scan the hive directory and register all symbols found.

        Returns number of symbols registered.
        """
        candles_dir = self._root / "equities" / "candles" / f"timeframe={timeframe}"
        if not candles_dir.exists():
            return 0

        count = 0
        for sym_dir in sorted(candles_dir.iterdir()):
            if not sym_dir.is_dir() or not sym_dir.name.startswith("symbol="):
                continue

            symbol = sym_dir.name.replace("symbol=", "")
            parquet_path = sym_dir / "data.parquet"
            if not parquet_path.exists():
                continue

            # Get stats using pandas (avoids PyArrow schema merge issues)
            try:
                import pandas as pd
                df = pd.read_parquet(parquet_path, columns=["timestamp"])
                total_rows = len(df)
                if total_rows == 0:
                    continue

                ts = pd.to_datetime(df["timestamp"])
                first_date = ts.min().date()
                last_date = ts.max().date()

                self.register_symbol(
                    symbol=symbol,
                    first_date=first_date,
                    last_date=last_date,
                    total_rows=total_rows,
                    timeframe=timeframe,
                    parquet_path=str(parquet_path),
                )
                count += 1
            except Exception as exc:
                logger.warning("Failed to scan %s: %s", symbol, exc)

        return count

    def record_quality(
        self,
        symbol: str,
        total_rows: int = 0,
        missing_candles: int = 0,
        duplicate_candles: int = 0,
        gap_days: int = 0,
        min_date: date | None = None,
        max_date: date | None = None,
        completeness_pct: float = 0.0,
        status: str = "OK",
        timeframe: str = "1m",
    ) -> None:
        """Record data quality metrics for a symbol."""
        from datetime import date as date_type
        check_date = date_type.today()
        self.conn.execute("""
            INSERT OR REPLACE INTO data_quality
            (symbol, check_date, timeframe, total_rows, missing_candles, duplicate_candles,
             gap_days, min_date, max_date, completeness_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [symbol, check_date, timeframe, total_rows, missing_candles, duplicate_candles,
              gap_days, min_date, max_date, completeness_pct, status])

    def summary(self) -> dict:
        """Get catalog summary."""
        symbols = self.conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        total_rows = self.conn.execute("SELECT COALESCE(SUM(total_rows), 0) FROM symbols").fetchone()[0]
        quality = self.conn.execute("SELECT COUNT(*) FROM data_quality").fetchone()[0]
        return {
            "symbols": symbols,
            "total_rows": total_rows,
            "quality_records": quality,
        }
