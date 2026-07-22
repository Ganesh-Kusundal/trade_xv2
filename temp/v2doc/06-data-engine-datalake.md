# 06 — Data Engine & DataLake

## 1. Overview

The Data Engine provides unified access to market data across all sources:
live streaming, historical APIs, and the local DataLake (DuckDB + Parquet).

```
┌─────────────────────────────────────────────────────────────┐
│                      DataEngine                             │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Live        │  │  Historical  │  │  DataLake        │  │
│  │  Ticks       │  │  Fetch       │  │  (DuckDB+Parquet)│  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └─────────────────┼────────────────────┘            │
│                           │                                 │
│                    ┌──────▼───────┐                         │
│                    │  Source      │                         │
│                    │  Selection   │                         │
│                    │  Policy      │                         │
│                    └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

## 2. Storage Architecture

### 2.1 DuckDB + Parquet

```
datalake/
├── raw/                          # Raw tick data (Parquet)
│   ├── NSE/
│   │   ├── RELIANCE/
│   │   │   ├── 2024-01-15.parquet
│   │   │   ├── 2024-01-16.parquet
│   │   │   └── ...
│   │   └── ...
│   └── BSE/
│       └── ...
│
├── bars/                         # OHLCV bars (Parquet)
│   ├── 1m/
│   │   ├── NSE_RELIANCE.parquet
│   │   ├── NSE_TCS.parquet
│   │   └── ...
│   ├── 5m/
│   │   └── ...
│   └── 1d/
│       └── ...
│
├── options/                      # Option chain snapshots
│   ├── NIFTY/
│   │   ├── 2024-01-15_15-30.parquet
│   │   └── ...
│   └── BANKNIFTY/
│       └── ...
│
└── catalog.db                    # DuckDB catalog (metadata + analytics)
```

### 2.2 Parquet Schema

```python
# Bars schema
bars_schema = {
    "symbol": "string",
    "exchange": "string",
    "timestamp": "timestamp[us]",  # UTC
    "open": "decimal(18, 4)",
    "high": "decimal(18, 4)",
    "low": "decimal(18, 4)",
    "close": "decimal(18, 4)",
    "volume": "int64",
    "oi": "int64",  # Open interest (futures/options)
}

# Ticks schema
ticks_schema = {
    "symbol": "string",
    "exchange": "string",
    "timestamp": "timestamp[us]",
    "last_price": "decimal(18, 4)",
    "bid": "decimal(18, 4)",
    "ask": "decimal(18, 4)",
    "bid_size": "int64",
    "ask_size": "int64",
    "volume": "int64",
}
```

## 3. DataCatalog

```python
# datalake/catalog.py

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from domain.ports.data_catalog import DataCatalogPort


logger = logging.getLogger(__name__)


class DataCatalog(DataCatalogPort):
    """
    Unified data access layer.

    Provides SQL-based access to market data stored in Parquet files.
    DuckDB serves as the analytical engine — no server required.
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
        self._db = duckdb.connect(str(base_path / "catalog.db"))
        self._setup_schema()

    def _setup_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS bars_metadata (
                symbol VARCHAR,
                exchange VARCHAR,
                timeframe VARCHAR,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                row_count BIGINT,
                file_path VARCHAR,
                PRIMARY KEY (symbol, exchange, timeframe)
            )
        """)

    # ── Query ─────────────────────────────────────────────────

    async def get_bars(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars from the data lake."""
        path = self._base_path / "bars" / timeframe / f"{exchange}_{symbol}.parquet"
        if not path.exists():
            logger.warning("No bars found for %s:%s @ %s", symbol, exchange, timeframe)
            return pd.DataFrame()

        query = f"""
            SELECT *
            FROM read_parquet('{path}')
            WHERE timestamp BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
            ORDER BY timestamp
        """
        return self._db.execute(query).fetchdf()

    async def get_quotes(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch tick data from the data lake."""
        date_range = pd.date_range(start, end, freq="D")
        frames = []
        for date in date_range:
            path = (
                self._base_path / "raw" / exchange / symbol
                / f"{date.strftime('%Y-%m-%d')}.parquet"
            )
            if path.exists():
                df = self._db.execute(f"""
                    SELECT *
                    FROM read_parquet('{path}')
                    WHERE timestamp BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
                """).fetchdf()
                frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames).sort_values("timestamp").reset_index(drop=True)

    async def get_option_chain(
        self,
        underlying: str,
        expiry: str,
        timestamp: datetime,
    ) -> pd.DataFrame:
        """Fetch option chain snapshot."""
        path = (
            self._base_path / "options" / underlying
            / f"{timestamp.strftime('%Y-%m-%d_%H-%M')}.parquet"
        )
        if not path.exists():
            return pd.DataFrame()

        query = f"""
            SELECT *
            FROM read_parquet('{path}')
            WHERE expiry = '{expiry}'
            ORDER BY strike, option_type
        """
        return self._db.execute(query).fetchdf()

    # ── Ingest ────────────────────────────────────────────────

    async def ingest_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> None:
        """Ingest OHLCV bars into the data lake."""
        path = self._base_path / "bars" / timeframe / f"{exchange}_{symbol}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Append mode: read existing, concat, write
        if path.exists():
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df]).drop_duplicates().sort_values("timestamp")

        df.to_parquet(path, index=False)

        # Update metadata
        self._db.execute("""
            INSERT OR REPLACE INTO bars_metadata
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            symbol, exchange, timeframe,
            df["timestamp"].min(), df["timestamp"].max(),
            len(df), str(path),
        ])

    async def ingest_ticks(
        self,
        symbol: str,
        exchange: str,
        df: pd.DataFrame,
    ) -> None:
        """Ingest tick data into the data lake."""
        date = df["timestamp"].dt.date.iloc[0]
        path = (
            self._base_path / "raw" / exchange / symbol
            / f"{date}.parquet"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df]).drop_duplicates().sort_values("timestamp")

        df.to_parquet(path, index=False)

    # ── Analytics ─────────────────────────────────────────────

    def query(self, sql: str) -> pd.DataFrame:
        """Execute arbitrary SQL against the data lake."""
        return self._db.execute(sql).fetchdf()

    def close(self) -> None:
        self._db.close()
```

## 4. DataEngine

```python
# application/data/data_engine.py

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from domain.ports.broker_adapter import BrokerAdapterPort
from domain.ports.data_catalog import DataCatalogPort
from shared.messaging.component import Component


logger = logging.getLogger(__name__)


class DataEngine(Component):
    """
    Unified data access with source selection policy.

    Decides whether to fetch from:
    1. DataLake (local cache) — fastest, may be stale
    2. Broker API (live) — always fresh, slower
    3. Hybrid — DataLake first, fill gaps from broker
    """

    def __init__(
        self,
        bus,
        catalog: DataCatalogPort,
        broker: Optional[BrokerAdapterPort] = None,
        prefer_local: bool = True,
    ) -> None:
        super().__init__(component_id="DataEngine", bus=bus)
        self._catalog = catalog
        self._broker = broker
        self._prefer_local = prefer_local

    async def get_bars(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1m",
    ) -> pd.DataFrame:
        """Fetch bars with source selection."""
        if self._prefer_local:
            df = await self._catalog.get_bars(symbol, exchange, start, end, timeframe)
            if not df.empty:
                return df

        # Fallback to broker
        if self._broker:
            df = await self._broker.get_history(symbol, exchange, start, end, timeframe)
            # Ingest into catalog for future use
            await self._catalog.ingest_bars(symbol, exchange, timeframe, df)
            return df

        return pd.DataFrame()

    async def get_quotes(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch tick data with source selection."""
        if self._prefer_local:
            df = await self._catalog.get_quotes(symbol, exchange, start, end)
            if not df.empty:
                return df

        # Ticks are not available from broker historical API
        # Must be captured via streaming
        logger.warning("No tick data available for %s:%s", symbol, exchange)
        return pd.DataFrame()

    async def get_live_quote(self, symbol: str, exchange: str):
        """Fetch current quote from broker."""
        if not self._broker:
            raise RuntimeError("No broker configured for live data")
        return await self._broker.get_quote(symbol, exchange)
```

## 5. Live Tick Pipeline

```python
# application/streaming/live_tick_pipeline.py

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Callable

from domain.entities.quote import Quote
from shared.messaging.component import Component


logger = logging.getLogger(__name__)


class LiveTickPipeline(Component):
    """
    Processes live ticks from streaming adapters.

    Responsibilities:
    1. Buffer ticks for real-time analytics
    2. Periodically flush to DataLake
    3. Dispatch to strategy callbacks
    """

    def __init__(
        self,
        bus,
        catalog,
        flush_interval: float = 60.0,  # seconds
    ) -> None:
        super().__init__(component_id="LiveTickPipeline", bus=bus)
        self._catalog = catalog
        self._flush_interval = flush_interval
        self._buffer: dict[tuple[str, str], list[Quote]] = defaultdict(list)
        self._callbacks: list[Callable] = []
        self._flush_task: asyncio.Task | None = None

    def _on_start(self) -> None:
        self._flush_task = asyncio.create_task(self._flush_loop())

    def _on_stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()

    def on_tick(self, quote: Quote) -> None:
        """Called by streaming adapter when a tick arrives."""
        key = (quote.symbol, quote.exchange)
        self._buffer[key].append(quote)

        # Dispatch to callbacks
        for cb in self._callbacks:
            try:
                cb(quote)
            except Exception as exc:
                logger.exception("Tick callback failed: %s", exc)

    def register_callback(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    async def _flush_loop(self) -> None:
        """Periodically flush buffer to DataLake."""
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        """Flush buffered ticks to DataLake."""
        for (symbol, exchange), quotes in self._buffer.items():
            if not quotes:
                continue

            df = self._quotes_to_df(quotes)
            await self._catalog.ingest_ticks(symbol, exchange, df)
            logger.debug("Flushed %d ticks for %s:%s", len(quotes), symbol, exchange)

        self._buffer.clear()

    def _quotes_to_df(self, quotes: list[Quote]) -> pd.DataFrame:
        import pandas as pd
        data = [
            {
                "symbol": q.symbol,
                "exchange": q.exchange,
                "timestamp": q.timestamp,
                "last_price": q.last_price.value,
                "bid": q.bid.value,
                "ask": q.ask.value,
                "bid_size": q.bid_size.value,
                "ask_size": q.ask_size.value,
                "volume": q.volume.value,
            }
            for q in quotes
        ]
        return pd.DataFrame(data)
```

## 6. Data Sync

```python
# datalake/ingestion/auto_sync.py

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from domain.ports.broker_adapter import BrokerAdapterPort
from domain.ports.data_catalog import DataCatalogPort


logger = logging.getLogger(__name__)


class AutoSync:
    """
    Automatically syncs historical data from broker to DataLake.

    Runs on schedule (e.g., daily at 6 AM) to fetch previous day's data.
    Supports incremental sync — only fetches missing date ranges.
    """

    def __init__(
        self,
        catalog: DataCatalogPort,
        broker: BrokerAdapterPort,
        symbols: list[tuple[str, str]],  # [(symbol, exchange), ...]
        timeframes: list[str] = ["1m", "5m", "15m", "1d"],
    ) -> None:
        self._catalog = catalog
        self._broker = broker
        self._symbols = symbols
        self._timeframes = timeframes

    async def sync_day(self, date: datetime) -> None:
        """Sync data for a specific date."""
        start = date.replace(hour=0, minute=0, second=0)
        end = date.replace(hour=23, minute=59, second=59)

        for symbol, exchange in self._symbols:
            for tf in self._timeframes:
                logger.info("Syncing %s:%s @ %s for %s", symbol, exchange, tf, date)
                df = await self._broker.get_history(symbol, exchange, start, end, tf)
                if not df.empty:
                    await self._catalog.ingest_bars(symbol, exchange, tf, df)
                    logger.info("Ingested %d bars", len(df))

    async def sync_range(self, start: datetime, end: datetime) -> None:
        """Sync data for a date range."""
        current = start
        while current <= end:
            await self.sync_day(current)
            current += timedelta(days=1)
```

## 7. Source Selection Policy

```python
# domain/policies/source_selection.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DataSource(Enum):
    DATALAKE = "datalake"
    BROKER = "broker"
    HYBRID = "hybrid"


@dataclass
class SourceSelectionPolicy:
    """
    Decides where to fetch data from.

    Rules:
    1. If data is in DataLake and fresh enough → DATALAKE
    2. If data is not in DataLake → BROKER
    3. If data is in DataLake but stale → HYBRID (fill gaps from broker)
    """

    max_staleness: float = 300.0  # seconds

    def select(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        catalog_has_data: bool,
        data_age: float | None = None,
    ) -> DataSource:
        if not catalog_has_data:
            return DataSource.BROKER

        if data_age is None or data_age > self.max_staleness:
            return DataSource.HYBRID

        return DataSource.DATALAKE
```

## 8. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| Storage | Ad hoc CSV/JSON | DuckDB + Parquet |
| Query interface | Custom parsers | SQL via DuckDB |
| Data sync | Manual scripts | AutoSync with incremental updates |
| Live ticks | In-memory only | Buffer + periodic flush to DataLake |
| Source selection | Hardcoded | Policy-based |
| Analytics | Pandas only | DuckDB SQL + Pandas |

## 9. Performance Targets

| Operation | Target | Rationale |
|---|---|---|
| Query 1 day of 1m bars | < 10 ms | Parquet columnar scan |
| Query 1 year of 1d bars | < 50 ms | Partition pruning |
| Ingest 1M ticks | < 5 s | Parquet write + DuckDB index |
| Live tick buffer | 100k ticks/sec | In-memory append |
