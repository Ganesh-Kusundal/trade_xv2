"""SQLite-based instrument cache manager.

Provides persistent, broker-agnostic instrument caching with:
- Daily refresh (TTL-based invalidation)
- Pluggable broker adapters
- Sub-second symbol resolution
- Transparent lazy refresh on first call after expiry
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

CACHE_VALIDITY_HOURS = 24


class BrokerInstrumentAdapter(ABC):
    """Abstract base for broker-specific instrument adapters."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """e.g., 'upstox', 'dhan', 'zerodha'"""
        ...

    @property
    @abstractmethod
    def table_name(self) -> str:
        """e.g., 'instruments_upstox'"""
        ...

    @abstractmethod
    def get_schema(self) -> str:
        """Return CREATE TABLE SQL for this broker."""
        ...

    @abstractmethod
    def get_indexes(self) -> list[str]:
        """Return CREATE INDEX SQL statements."""
        ...

    @abstractmethod
    def to_row(self, instrument: Any) -> dict:
        """Convert broker instrument to SQLite row dict."""
        ...

    @abstractmethod
    def from_row(self, row: dict) -> Any:
        """Convert SQLite row back to broker instrument object."""
        ...

    @abstractmethod
    def resolve_symbol(self, symbol: str, exchange: str) -> dict | None:
        """Query SQLite and return raw row for symbol+exchange."""
        ...

    @abstractmethod
    def build_api_key(self, row: dict) -> str:
        """Build the broker-specific API identifier from a SQLite row.

        Examples:
        - Upstox: "NSE_EQ|INE002A01018"
        - Dhan: "1333"
        - Zerodha: "2885"
        """
        ...

    @abstractmethod
    def build_api_metadata(self, row: dict) -> dict:
        """Return extra broker-specific metadata needed for API calls.

        Examples:
        - Upstox: {"exchange_segment": "NSE_EQ"}
        - Dhan: {"exchange_segment": "NSE_EQ"}
        """
        ...


class InstrumentCacheManager:
    """Manages persistent SQLite instrument cache for all brokers."""

    def __init__(self, db_path: Path = Path(".cache/instruments.db")):
        self.db_path = db_path
        self._adapters: dict[str, BrokerInstrumentAdapter] = {}
        self._loaders: dict[str, Callable] = {}  # broker → loader function
        self._refresh_lock = threading.RLock()
        self._ensure_metadata_table()

    def register_adapter(self, adapter: BrokerInstrumentAdapter):
        """Register a broker adapter (call at broker init time)."""
        self._adapters[adapter.broker_name] = adapter
        self._ensure_broker_table(adapter)

    def register_loader(self, broker: str, loader_fn: Callable):
        """Register a loader function for transparent lazy refresh.
        
        The loader function should return a list of instrument objects
        that the adapter can convert to rows via to_row().
        
        Example:
            cache.register_loader("upstox", lambda: loader.load(cache_path))
        """
        self._loaders[broker] = loader_fn
        logger.info(f"Registered loader for {broker}")

    def get_adapter(self, broker: str) -> BrokerInstrumentAdapter:
        """Get registered adapter for a broker."""
        if broker not in self._adapters:
            raise KeyError(f"No adapter registered for broker: {broker}")
        return self._adapters[broker]

    def _ensure_metadata_table(self):
        """Create cache_metadata table if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    broker TEXT PRIMARY KEY,
                    last_refresh TIMESTAMP NOT NULL,
                    instrument_count INTEGER NOT NULL,
                    cache_version INTEGER DEFAULT 1,
                    source_url TEXT,
                    adapter_class TEXT
                )
                """
            )
            conn.commit()

    def _ensure_broker_table(self, adapter: BrokerInstrumentAdapter):
        """Create broker-specific table using adapter schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(adapter.get_schema())
            for idx_sql in adapter.get_indexes():
                conn.execute(idx_sql)
            conn.commit()

    def is_cache_valid(self, broker: str, max_age_hours: int = CACHE_VALIDITY_HOURS) -> bool:
        """Check if cache exists and is fresher than max_age_hours."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT last_refresh FROM cache_metadata WHERE broker = ?",
                (broker,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            last_refresh = row[0]
            # Parse timestamp and check age
            try:
                from datetime import datetime

                if " " in last_refresh:
                    refresh_time = datetime.strptime(last_refresh, "%Y-%m-%d %H:%M:%S")
                else:
                    refresh_time = datetime.fromisoformat(last_refresh)

                age_seconds = (datetime.now() - refresh_time).total_seconds()
                age_hours = age_seconds / 3600
                return age_hours < max_age_hours
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse cache timestamp: {e}")
                return False

    def resolve_symbol(self, broker: str, symbol: str, exchange: str) -> dict | None:
        """Fast symbol resolution from SQLite (< 100ms).
        
        Transparently refreshes cache if expired (lazy refresh on first call).
        Thread-safe: uses double-checked locking pattern.
        """
        # Check if cache is valid (fast path, no lock)
        if not self.is_cache_valid(broker):
            # Trigger lazy refresh (acquires lock internally)
            self._lazy_refresh(broker)
        
        adapter = self.get_adapter(broker)
        return adapter.resolve_symbol(symbol, exchange)

    def search(
        self, broker: str, prefix: str, exchange: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Search instruments by symbol prefix."""
        adapter = self.get_adapter(broker)
        table = adapter.table_name

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if exchange:
                query = f"""
                    SELECT * FROM {table}
                    WHERE symbol LIKE ? AND exchange = ?
                    LIMIT ?
                """
                cursor = conn.execute(query, (f"{prefix}%", exchange, limit))
            else:
                query = f"""
                    SELECT * FROM {table}
                    WHERE symbol LIKE ?
                    LIMIT ?
                """
                cursor = conn.execute(query, (f"{prefix}%", limit))

            return [dict(row) for row in cursor.fetchall()]

    def cache_instruments(self, broker: str, instruments: list[Any]) -> int:
        """Bulk insert instruments using adapter's to_row()."""
        adapter = self.get_adapter(broker)
        table = adapter.table_name
        rows = [adapter.to_row(inst) for inst in instruments]

        if not rows:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            # Clear existing data
            conn.execute(f"DELETE FROM {table}")

            # Insert all rows
            columns = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(columns))
            column_str = ", ".join(columns)
            insert_sql = f"INSERT INTO {table} ({column_str}) VALUES ({placeholders})"

            conn.executemany(insert_sql, [tuple(row[col] for col in columns) for row in rows])

            # Update metadata
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_metadata
                (broker, last_refresh, instrument_count, cache_version, source_url, adapter_class)
                VALUES (?, datetime('now'), ?, 1, NULL, ?)
                """,
                (broker, len(rows), adapter.__class__.__name__),
            )
            conn.commit()

        logger.info(f"Cached {len(rows)} instruments for {broker}")
        return len(rows)

    def refresh(self, broker: str, loader) -> int:
        """Download fresh instruments and update cache."""
        # Call loader to download and parse
        instruments = loader.load_instruments()

        # Cache them
        return self.cache_instruments(broker, instruments)

    def get_instrument_count(self, broker: str) -> int:
        """Get number of cached instruments for a broker."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT instrument_count FROM cache_metadata WHERE broker = ?",
                (broker,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def delete_cache(self, broker: str):
        """Delete all cached data for a broker."""
        adapter = self.get_adapter(broker)
        table = adapter.table_name

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM cache_metadata WHERE broker = ?", (broker,))
            conn.commit()

    def _lazy_refresh(self, broker: str):
        """Refresh cache transparently if loader is registered.
        
        Thread-safe: only one refresh happens even with concurrent calls.
        Graceful degradation: if refresh fails, logs warning and continues.
        """
        with self._refresh_lock:
            # Double-check after acquiring lock (another thread may have refreshed)
            if self.is_cache_valid(broker):
                return
            
            loader_fn = self._loaders.get(broker)
            if not loader_fn:
                logger.debug(f"No loader registered for {broker}, skipping refresh")
                return
            
            try:
                logger.info(f"Triggering lazy instrument refresh for {broker}...")
                start = time.time()
                
                # Call loader to get fresh instruments
                instruments = loader_fn()
                if not instruments:
                    logger.warning(f"Loader returned no instruments for {broker}")
                    return
                
                # Cache them
                self.cache_instruments(broker, instruments)
                
                elapsed = time.time() - start
                logger.info(
                    f"Lazy refresh complete for {broker}: "
                    f"{len(instruments)} instruments in {elapsed:.2f}s"
                )
            except Exception as e:
                logger.warning(
                    f"Lazy refresh failed for {broker}: {e}",
                    exc_info=True,
                )
                # Graceful degradation: continue with stale/empty cache
