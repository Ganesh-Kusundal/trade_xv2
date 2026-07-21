"""DuckDB Catalog — metadata store for the data lake.

Tracks: symbols, date ranges, row counts, data quality, missing data.
Provides fast queries over Parquet files without loading them.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import duckdb

from datalake.core.duckdb_utils import duckdb_connection, get_pool
from datalake.core.paths import timeframe_partition_dir
from domain.market_enums import ExchangeId
from datalake.core.symbols import normalize_symbol_for_storage

logger = logging.getLogger(__name__)


class DataCatalog:
    """DuckDB-backed metadata catalog for the data lake."""

    _schema_lock = threading.Lock()

    def __init__(self, root: str | None = None, read_only: bool = False) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS

            root = DEFAULT_DATA_PATHS.lake_root
        self._root = Path(root)
        self._db_path = self._root / "catalog.duckdb"
        self._read_only = read_only
        if not read_only:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None
        if not read_only:
            self._ensure_schema()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Return the cached read-write connection (write mode only)."""
        if self._read_only:
            raise RuntimeError(
                "DataCatalog is read-only; use _connection() context manager for reads"
            )
        if self._conn is None:
            self._conn = get_pool().acquire(self._db_path, read_only=False)
        return self._conn

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield a DuckDB connection appropriate for read or write access."""
        if write and self._read_only:
            raise duckdb.InvalidInputException("DataCatalog is read-only; writes are not allowed")
        if self._read_only or not write:
            with duckdb_connection(self._db_path, read_only=True) as conn:
                yield conn
        else:
            yield self.conn

    def close(self) -> None:
        if self._conn is not None:
            get_pool().release(self._db_path)
            self._conn = None

    def _ensure_schema(self) -> None:
        """Initialize schema once under a class-level lock."""
        with self._schema_lock:
            self._init_schema(self.conn)

    def _init_schema(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Create catalog tables if they don't exist."""
        self._create_symbols_table(conn)
        self._create_data_quality_table(conn)
        self._create_download_jobs_table(conn)
        self._create_universe_history_table(conn)
        self._create_symbol_metadata_history_table(conn)
        self._create_data_versions_table(conn)

        from datalake.core.migrations import apply_migrations

        apply_migrations(conn)

    @staticmethod
    def _create_symbols_table(conn: duckdb.DuckDBPyConnection) -> None:
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

    @staticmethod
    def _create_data_quality_table(conn: duckdb.DuckDBPyConnection) -> None:
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

    @staticmethod
    def _create_download_jobs_table(conn: duckdb.DuckDBPyConnection) -> None:
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

    @staticmethod
    def _create_universe_history_table(conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS universe_history (
                universe VARCHAR,
                symbol VARCHAR,
                effective_date DATE NOT NULL,
                end_date DATE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (universe, symbol, effective_date)
            )
        """)

    @staticmethod
    def _create_symbol_metadata_history_table(conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS symbol_metadata_history (
                symbol VARCHAR,
                effective_date DATE NOT NULL,
                end_date DATE,
                lot_size INTEGER,
                tick_size DOUBLE,
                sector VARCHAR,
                isin VARCHAR,
                instrument_type VARCHAR DEFAULT 'EQUITY',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, effective_date)
            )
        """)

    @staticmethod
    def _create_data_versions_table(conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_versions (
                table_name VARCHAR,
                version_id BIGINT,
                min_event_time TIMESTAMP,
                max_event_time TIMESTAMP,
                min_published_at TIMESTAMP,
                max_published_at TIMESTAMP,
                row_count BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (table_name, version_id)
            )
        """)

    def register_symbol(
        self,
        symbol: str,
        exchange: str = ExchangeId.NSE,
        first_date: date | None = None,
        last_date: date | None = None,
        total_rows: int = 0,
        timeframe: str = "1m",
        parquet_path: str = "",
        sector: str | None = None,
        isin: str | None = None,
        **kwargs,
    ) -> None:
        if self._read_only:
            raise duckdb.InvalidInputException("DataCatalog is read-only; writes are not allowed")
        symbol = normalize_symbol_for_storage(symbol)
        # Empty sector/isin means "leave existing value" on conflict (ingest rarely knows them).
        sector = "" if sector is None else sector
        isin = "" if isin is None else isin
        self.conn.execute(
            """
            INSERT INTO symbols AS s
            (symbol, exchange, sector, isin, first_date, last_date, total_rows,
             timeframe, parquet_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT (symbol) DO UPDATE SET
                exchange = excluded.exchange,
                sector = CASE WHEN excluded.sector = '' THEN s.sector ELSE excluded.sector END,
                isin = CASE WHEN excluded.isin = '' THEN s.isin ELSE excluded.isin END,
                first_date = excluded.first_date,
                last_date = excluded.last_date,
                total_rows = excluded.total_rows,
                timeframe = excluded.timeframe,
                parquet_path = excluded.parquet_path,
                updated_at = now()
            """,
            [
                symbol,
                exchange,
                sector,
                isin,
                first_date,
                last_date,
                total_rows,
                timeframe,
                parquet_path,
            ],
        )

    def backfill_sectors(
        self,
        mapping: dict[str, str],
        *,
        isin_by_symbol: dict[str, str] | None = None,
    ) -> int:
        """Update ``symbols.sector`` (and optional ISIN) for known tickers.

        Returns number of catalog rows that exist in *mapping* and were written.
        """
        if self._read_only:
            raise duckdb.InvalidInputException("DataCatalog is read-only; writes are not allowed")
        updated = 0
        isin_by_symbol = isin_by_symbol or {}
        for symbol, sector in mapping.items():
            sym = normalize_symbol_for_storage(symbol)
            exists = self.conn.execute("SELECT 1 FROM symbols WHERE symbol = ?", [sym]).fetchone()
            if exists is None:
                continue
            isin = isin_by_symbol.get(sym) or isin_by_symbol.get(symbol) or ""
            if isin:
                self.conn.execute(
                    """
                    UPDATE symbols
                    SET sector = ?, isin = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = ?
                    """,
                    [sector, isin, sym],
                )
            else:
                self.conn.execute(
                    """
                    UPDATE symbols
                    SET sector = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = ?
                    """,
                    [sector, sym],
                )
            updated += 1
        return updated

    def get_symbol(self, symbol: str) -> dict | None:
        """Get symbol metadata."""
        symbol = normalize_symbol_for_storage(symbol)
        with self._connection() as conn:
            result = conn.execute("SELECT * FROM symbols WHERE symbol = ?", [symbol]).fetchone()
            if result is None:
                return None
            cursor = conn.execute("SELECT * FROM symbols WHERE symbol = ?", [symbol])
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, result, strict=False))

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        """List all registered symbols."""
        with self._connection() as conn:
            results = conn.execute(
                "SELECT symbol FROM symbols WHERE timeframe = ? ORDER BY symbol",
                [timeframe],
            ).fetchall()
            return [r[0] for r in results]

    def get_parquet_path(self, symbol: str, timeframe: str = "1m") -> Path | None:
        """Get the Parquet file path for a symbol."""
        with self._connection() as conn:
            row = conn.execute(
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
        candles_dir = timeframe_partition_dir(str(self._root), timeframe)
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

    def register_universe_snapshot(
        self, universe: str, symbols: list[str], as_of_date: date | None = None
    ) -> int:
        if as_of_date is None:
            as_of_date = date.today()

        self.conn.execute(
            """
            UPDATE universe_history
            SET end_date = ?
            WHERE universe = ? AND end_date IS NULL
        """,
            [as_of_date, universe],
        )

        count = 0
        for symbol in symbols:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO universe_history
                (universe, symbol, effective_date)
                VALUES (?, ?, ?)
            """,
                [universe, symbol, as_of_date],
            )
            count += 1

        return count

    def get_universe_as_of(self, universe: str, as_of_date: date) -> list[str]:
        result = self.conn.execute(
            """
            SELECT symbol FROM universe_history
            WHERE universe = ?
              AND effective_date <= ?
              AND (end_date IS NULL OR end_date > ?)
            ORDER BY symbol
        """,
            [universe, as_of_date, as_of_date],
        ).fetchall()
        return [r[0] for r in result]

    def register_symbol_metadata_snapshot(
        self,
        symbol: str,
        lot_size: int = 1,
        tick_size: float = 0.05,
        sector: str = "",
        isin: str = "",
        instrument_type: str = "EQUITY",
        as_of_date: date | None = None,
    ) -> None:
        if as_of_date is None:
            as_of_date = date.today()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO symbol_metadata_history
            (symbol, effective_date, lot_size, tick_size, sector, isin, instrument_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            [symbol, as_of_date, lot_size, tick_size, sector, isin, instrument_type],
        )

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
        self.conn.execute(
            """
            INSERT OR REPLACE INTO data_quality
            (symbol, check_date, timeframe, total_rows, missing_candles, duplicate_candles,
             gap_days, min_date, max_date, completeness_pct, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                symbol,
                check_date,
                timeframe,
                total_rows,
                missing_candles,
                duplicate_candles,
                gap_days,
                min_date,
                max_date,
                completeness_pct,
                status,
            ],
        )

    def summary(self) -> dict:
        """Get catalog summary."""
        with self._connection() as conn:
            symbols = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            total_rows = conn.execute(
                "SELECT COALESCE(SUM(total_rows), 0) FROM symbols"
            ).fetchone()[0]
            quality = conn.execute("SELECT COUNT(*) FROM data_quality").fetchone()[0]
            return {
                "symbols": symbols,
                "total_rows": total_rows,
                "quality_records": quality,
            }
