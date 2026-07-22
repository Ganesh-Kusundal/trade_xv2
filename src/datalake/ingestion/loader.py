"""HistoricalDataLoader — download and store data from brokers.

Uses Dhan/Upstox gateways to fetch historical data and write to Parquet.
Only used for initial load and gap filling — not for research.

All timestamps are normalized to IST (naive datetime) before writing.
All symbols are normalized (uppercased, stripped) before writing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

import pandas as pd
import pyarrow as pa

from datalake.core.io import atomic_parquet_write
from datalake.core.paths import symbol_partition_path
from datalake.core.schema import enforce_canonical_schema
from datalake.core.symbols import normalize_symbol_for_storage
from datalake.exchange_registry import (
    COMPLETENESS_OK_FRACTION,
    expected_candles_per_day,
    get_active_exchange_code,
    trading_days_between,
)
from datalake.ingestion.broker_selection import _TIMEFRAME_ALIASES, select_historical_source
from domain.ports.historical_fetch import HistoricalFetchPort
from infrastructure.batch_executor import batch_execute

logger = logging.getLogger(__name__)

# ponytail: retention is config-only — compaction script can read this; hot path never deletes.
DATALAKE_RETENTION_DAYS: int = int(__import__("os").getenv("DATALAKE_RETENTION_DAYS", "0") or "0")


def parquet_retention_days() -> int:
    """Configured parquet retention (0 = disabled / grow unbounded)."""
    return max(0, DATALAKE_RETENTION_DAYS)


def _session_bounds():
    """Return (open, close) from the active trading calendar."""
    from datalake.exchange_registry import _get_calendar

    return _get_calendar().session_bounds(None)


class WriteResult(NamedTuple):
    """Result of a merge-write. ``rows``/``invalid_dropped`` describe the
    incoming fetch only (unchanged public contract used by callers'
    "rows synced this run" logging); ``total_rows``/``first_ts``/``last_ts``
    describe the file on disk *after* merging with any pre-existing data,
    for catalog registration."""

    rows: int
    invalid_dropped: int
    total_rows: int
    first_ts: pd.Timestamp | None
    last_ts: pd.Timestamp | None


class HistoricalDataLoader:
    """Download historical data from brokers and store as Parquet."""

    def __init__(self, root: str | None = None, catalog=None) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS

            root = DEFAULT_DATA_PATHS.lake_root
        self._root = Path(root)
        self._catalog = catalog

    def download_symbol(
        self,
        symbol: str,
        gateway: Any = None,
        years: int = 5,
        timeframe: str = "1m",
        exchange: str | None = None,
        *,
        gateways: dict[str, Any] | None = None,
        fetch_fn: Callable[[str, str, str, int], pd.DataFrame] | None = None,
        lookback_days: int | None = None,
    ) -> dict:
        """Download historical data for a single symbol.

        Three fetch strategies, in precedence order:

        1. *fetch_fn* -- ``(symbol, exchange, timeframe, lookback_days) ->
           DataFrame``. The recommended path for real syncs: the caller
           supplies a quota-aware, multi-broker-federated fetcher (see
           ``scripts/sync_datalake.py``'s use of
           ``application.composer.market_data.MarketDataComposer
           .fetch_historical`` -- not imported here, since ``datalake``
           doesn't depend on ``application``; the caller adapts it to
           this narrow callable shape).
        2. *gateway* -- a single broker gateway (existing behavior,
           unchanged). Chunked via :meth:`_fetch_history_chunked` but no
           pre-emptive rate limiting or cross-broker failover.
        3. *gateways* -- a ``{broker_id: gateway}`` dict; the broker with
           the largest historical range for *timeframe* is auto-selected
           via :func:`select_historical_source`, then fetched via (2).

        Returns
        -------
        Dict with keys: rows, duplicates_dropped, invalid_dropped.
        """
        if fetch_fn is None and gateway is None:
            if not gateways:
                raise ValueError(
                    "download_symbol requires one of fetch_fn=, gateway=, or gateways="
                )
            _, gateway = select_historical_source(timeframe, gateways)

        symbol = normalize_symbol_for_storage(symbol)
        if exchange is None:
            exchange = get_active_exchange_code()
        # Let fetch failures (rate limits, network errors, ...) propagate.
        # Every caller (sync_datalake.py, download_universe)
        # already wraps its per-symbol call in batch_execute(), which
        # isolates the exception per-item and reports it via on_error --
        # swallowing it here instead made real failures indistinguishable
        # from "genuinely nothing new" (both returned rows=0), which
        # silently misreported a batch's rate-limited failures as
        # "already up to date" in run summaries.
        lookback_days = lookback_days if lookback_days is not None else years * 365
        if fetch_fn is not None:
            df = fetch_fn(symbol, exchange, timeframe, lookback_days)
        else:
            df = self._fetch_history_chunked(
                gateway, symbol, exchange, timeframe, lookback_days=lookback_days
            )

        if df is None or df.empty:
            logger.warning("No data returned for %s", symbol)
            return {"rows": 0, "duplicates_dropped": 0, "invalid_dropped": 0}

        df = self._normalize(df, symbol, exchange, timeframe)
        if df.empty:
            return {"rows": 0, "duplicates_dropped": 0, "invalid_dropped": 0}

        # Dedup with logging
        dup_count = df.duplicated(subset=["timestamp"]).sum()
        if dup_count > 0:
            logger.warning("%s: dropping %d duplicate timestamps", symbol, dup_count)
        df = df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")

        # Validate intraday completeness
        if timeframe in ("1m", "5m", "15m", "30m"):
            completeness = self._check_intraday_completeness(df, timeframe)
            if completeness < COMPLETENESS_OK_FRACTION:
                logger.warning(
                    "%s: Intraday completeness only %.1f%% (expected ~375 candles/day for 1m)",
                    symbol,
                    completeness * 100,
                )

        # Write to Parquet (merges with any existing data on disk)
        result = self._write_parquet(df, symbol, timeframe)
        logger.info(
            "Downloaded %s: %d rows fetched (%d invalid dropped), %d total on disk",
            symbol,
            result.rows,
            result.invalid_dropped,
            result.total_rows,
        )

        # Register in catalog — reflects the merged on-disk state, not just
        # this fetch, so catalog metadata never drifts from reality after
        # an incremental (shorter-window) sync.
        if self._catalog and result.total_rows > 0:
            self._catalog.register_symbol(
                symbol=symbol,
                exchange=exchange,
                first_date=result.first_ts.date(),
                last_date=result.last_ts.date(),
                total_rows=result.total_rows,
                timeframe=timeframe,
                parquet_path=str(self._parquet_path(symbol, timeframe)),
            )

        return {
            "rows": result.rows,
            "duplicates_dropped": dup_count,
            "invalid_dropped": result.invalid_dropped,
        }

    def download_universe(
        self,
        universe: str,
        gateway: Any = None,
        years: int = 5,
        timeframe: str = "1m",
        *,
        gateways: dict[str, Any] | None = None,
        fetch_fn: Callable[[str, str, str, int], pd.DataFrame] | None = None,
    ) -> dict[str, dict[str, int]]:
        """Download data for all symbols in a universe.

        See :meth:`download_symbol` for the *fetch_fn* / *gateway* vs
        *gateways* (auto-select) contract -- when *gateway*/*gateways* is
        used, the same broker is resolved once here and passed to every
        symbol's download; *fetch_fn* is passed through as-is (it's
        already broker-agnostic).
        """
        if fetch_fn is None and gateway is None:
            if not gateways:
                raise ValueError(
                    "download_universe requires one of fetch_fn=, gateway=, or gateways="
                )
            _, gateway = select_historical_source(timeframe, gateways)

        import csv

        from datalake.core.schema import UNIVERSE_FILES

        path = UNIVERSE_FILES.get(universe)
        if not path:
            logger.error("Unknown universe: %s", universe)
            return {}

        p = Path(path)
        if not p.exists():
            p = self._root.parent / path
        if not p.exists():
            logger.error("Universe file not found: %s", path)
            return {}

        with open(p) as f:
            reader = csv.DictReader(f)
            symbols = [row["symbol"] for row in reader]

        from config.indices import is_index
        from datalake.ingestion.sync_manifest import add_symbol_to_manifest

        for sym in symbols:
            asset = "indices" if is_index(sym) else "equities"
            add_symbol_to_manifest(str(self._root), sym, asset)

        def _download_one(sym: str) -> dict:
            logger.info("Downloading %s...", sym)
            return self.download_symbol(
                sym, gateway, years=years, timeframe=timeframe, fetch_fn=fetch_fn
            )

        def _on_error(sym: str, exc: Exception) -> None:
            logger.error("Failed to download %s: %s", sym, exc)

        raw_results = batch_execute(
            symbols,
            _download_one,
            on_error=_on_error,
        )

        # Normalize keys (download_symbol also normalizes internally)
        results = {normalize_symbol_for_storage(sym): res for sym, res in raw_results.items()}

        total_rows = sum(r["rows"] for r in results.values())
        logger.info(
            "Universe %s: %d symbols, %d total rows",
            universe,
            len(results),
            total_rows,
        )
        return results

    def detect_internal_gap_ranges(
        self, symbol: str, timeframe: str = "1m"
    ) -> list[tuple[date, date]]:
        """Return contiguous missing **trading-day** ranges within on-disk history."""
        symbol = normalize_symbol_for_storage(symbol)
        path = self._parquet_path(symbol, timeframe)
        if not path.exists():
            return []
        try:
            df = pd.read_parquet(path)
        except Exception:
            return []
        if df.empty:
            return []
        ts = pd.to_datetime(df["timestamp"])
        dates_with_data = set(ts.dt.date)
        start = min(dates_with_data)
        end = max(dates_with_data)
        trading_days = trading_days_between(start, end)
        ranges: list[tuple[date, date]] = []
        i = 0
        while i < len(trading_days):
            d = trading_days[i]
            if d in dates_with_data:
                i += 1
                continue
            gap_start = d
            while i < len(trading_days) and trading_days[i] not in dates_with_data:
                i += 1
            ranges.append((gap_start, trading_days[i - 1]))
        return ranges

    def _repair_internal_gaps(
        self,
        symbol: str,
        gateway: Any,
        timeframe: str,
        *,
        exchange: str | None,
        gateways: dict[str, Any] | None,
        fetch_fn: HistoricalFetchPort | None,
    ) -> int:
        """Phase B: fill holes between first and last on-disk trading days."""
        ranges = self.detect_internal_gap_ranges(symbol, timeframe)
        if not ranges:
            return 0
        total = 0
        today = datetime.now().date()
        for gap_start, gap_end in ranges:
            range_days = (gap_end - gap_start).days + 1
            lookback_days = (today - gap_start).days + 2
            logger.info(
                "%s: repairing internal gap %s..%s (%d trading days)",
                symbol,
                gap_start,
                gap_end,
                range_days,
            )
            rows = self.download_symbol(
                symbol,
                gateway,
                timeframe=timeframe,
                exchange=exchange,
                gateways=gateways,
                fetch_fn=fetch_fn,
                lookback_days=lookback_days,
            )["rows"]
            if rows == 0:
                raise RuntimeError(
                    f"{symbol}: internal gap {gap_start}..{gap_end} "
                    "detected but no broker returned data"
                )
            total += rows
        return total

    def _repair_tail_gap(
        self,
        symbol: str,
        gateway: Any,
        timeframe: str,
        *,
        exchange: str | None,
        gateways: dict[str, Any] | None,
        fetch_fn: HistoricalFetchPort | None,
    ) -> int:
        """Phase A: fill tail gap from last on-disk bar through today."""
        existing_path = self._parquet_path(symbol, timeframe)
        if not existing_path.exists():
            return self.download_symbol(
                symbol,
                gateway,
                years=5,
                timeframe=timeframe,
                exchange=exchange,
                gateways=gateways,
                fetch_fn=fetch_fn,
            )["rows"]

        # Catalog fast path: when last_date is clearly before today, skip
        # reading the full parquet file just to learn the same last_date.
        if self._catalog is not None:
            row = self._catalog.get_symbol(symbol)
            if row and row.get("last_date") is not None:
                last_date_from_catalog = pd.Timestamp(row["last_date"])
                today = datetime.now().date()
                if last_date_from_catalog.date() < today:
                    days_missing = (today - last_date_from_catalog.date()).days
                    lookback_days = max(days_missing, 1) + 2
                    logger.info(
                        "%s: catalog last_date=%s, downloading %d missing days (fast path)",
                        symbol,
                        last_date_from_catalog.date(),
                        max(days_missing, 1),
                    )
                    rows = self.download_symbol(
                        symbol,
                        gateway,
                        timeframe=timeframe,
                        exchange=exchange,
                        gateways=gateways,
                        fetch_fn=fetch_fn,
                        lookback_days=lookback_days,
                    )["rows"]
                    if rows == 0:
                        raise RuntimeError(
                            f"{symbol}: gap of {max(days_missing, 1)}d detected "
                            "but no broker returned data"
                        )
                    return rows

        try:
            existing = pd.read_parquet(existing_path)
        except Exception:
            return self.download_symbol(
                symbol,
                gateway,
                years=5,
                timeframe=timeframe,
                exchange=exchange,
                gateways=gateways,
                fetch_fn=fetch_fn,
            )["rows"]

        if existing.empty:
            return self.download_symbol(
                symbol,
                gateway,
                years=5,
                timeframe=timeframe,
                exchange=exchange,
                gateways=gateways,
                fetch_fn=fetch_fn,
            )["rows"]

        ts = pd.to_datetime(existing["timestamp"])
        last_date = ts.max()
        today = datetime.now().date()
        days_missing = (today - last_date.date()).days

        incomplete_day = False
        if timeframe in ("1m", "5m", "15m", "30m"):
            last_day_candles = (ts.dt.date == last_date.date()).sum()
            expected_last_day = expected_candles_per_day(timeframe)
            if last_day_candles < expected_last_day * COMPLETENESS_OK_FRACTION:
                incomplete_day = True
                logger.warning(
                    "%s: Last day incomplete (%d/%d candles)",
                    symbol,
                    last_day_candles,
                    expected_last_day,
                )

        if days_missing <= 0 and not incomplete_day:
            logger.info("%s: tail up to date", symbol)
            return 0

        lookback_days = max(days_missing, 1) + 2
        logger.info("%s: downloading %d missing tail days", symbol, max(days_missing, 1))
        rows = self.download_symbol(
            symbol,
            gateway,
            timeframe=timeframe,
            exchange=exchange,
            gateways=gateways,
            fetch_fn=fetch_fn,
            lookback_days=lookback_days,
        )["rows"]
        if rows == 0:
            raise RuntimeError(
                f"{symbol}: gap of {max(days_missing, 1)}d detected but no broker returned data"
            )
        return rows

    def repair_missing(
        self,
        symbol: str,
        gateway: Any = None,
        timeframe: str = "1m",
        *,
        exchange: str | None = None,
        gateways: dict[str, Any] | None = None,
        fetch_fn: HistoricalFetchPort | None = None,
        repair_scope: Literal["tail", "internal", "all"] = "all",
    ) -> int:
        """Download only missing data for a symbol -- the standard
        auto-detect-and-sync entry point: compares on-disk state against
        the broker, fetches only the missing window, and merges it in
        (see :meth:`_write_parquet`) rather than replacing the file.

        Invoked by :func:`datalake.ingestion.auto_sync.sync_all` and
        :meth:`datalake.DataLake.sync`. See :meth:`download_symbol` for the
        *fetch_fn* / *gateway* contract (:class:`domain.ports.historical_fetch.HistoricalFetchPort`).

        ``repair_scope``:
        - ``"tail"``: Phase A only (last bar → today) — daily sync.
        - ``"internal"``: Phase B only (mid-history holes) — slow backfill job.
        - ``"all"``: both phases.
        """
        symbol = normalize_symbol_for_storage(symbol)
        rows = 0
        if repair_scope in ("tail", "all"):
            rows += self._repair_tail_gap(
                symbol,
                gateway,
                timeframe,
                exchange=exchange,
                gateways=gateways,
                fetch_fn=fetch_fn,
            )
        if repair_scope in ("internal", "all"):
            rows += self._repair_internal_gaps(
                symbol,
                gateway,
                timeframe,
                exchange=exchange,
                gateways=gateways,
                fetch_fn=fetch_fn,
            )
        return rows

    def _fetch_history_chunked(
        self,
        gateway: Any,
        symbol: str,
        exchange: str,
        timeframe: str,
        lookback_days: int,
    ) -> pd.DataFrame:
        """Fetch *lookback_days* of history, splitting into chunks no
        larger than the broker's own ``max_chunk_days`` for *timeframe*.

        gateway.history(..., lookback_days=N) sends N as one request with
        no chunking. Dhan's intraday endpoint hard-rejects any single
        request spanning more than 90 days (DH-905: "Data for Intraday
        Charts can be fetched for 90 days at a time") -- the exact limit
        already recorded in BrokerCapabilities.historical_windows and
        used by select_historical_source(). Reusing that same data here
        instead of a second hardcoded "90".
        """
        max_chunk = self._max_chunk_days(gateway, timeframe)
        if lookback_days <= max_chunk:
            return gateway.history(
                symbol, exchange=exchange, timeframe=timeframe, lookback_days=lookback_days
            )

        today = datetime.now().date()
        overall_from = today - pd.Timedelta(days=lookback_days)
        frames: list[pd.DataFrame] = []
        chunk_start = overall_from
        while chunk_start < today:
            chunk_end = min(chunk_start + pd.Timedelta(days=max_chunk), today)
            page = gateway.history(
                symbol,
                exchange=exchange,
                timeframe=timeframe,
                from_date=str(chunk_start),
                to_date=str(chunk_end),
            )
            if page is not None and not page.empty:
                frames.append(page)
            chunk_start = chunk_end + pd.Timedelta(days=1)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @staticmethod
    def _max_chunk_days(gateway: Any, timeframe: str, default: int = 90) -> int:
        """Read the broker's max_chunk_days for *timeframe*; a conservative
        default (Dhan's actual intraday cap) if capabilities aren't
        available, so an unrecognised gateway still degrades safely
        rather than sending an oversized request."""
        target_tf = _TIMEFRAME_ALIASES.get(timeframe, timeframe)
        try:
            windows = gateway.capabilities().historical_windows
        except Exception:
            return default
        for window in windows:
            if window.timeframe == target_tf:
                return window.max_chunk_days
        return default

    def _normalize(
        self, df: pd.DataFrame, symbol: str, exchange: str, timeframe: str = "1m"
    ) -> pd.DataFrame:
        """Normalize broker DataFrame to canonical schema (IST timestamps)."""
        from datalake.ingestion.normalize import (
            normalize_to_canonical,
            rename_columns,
        )

        # Check required columns exist after rename
        renamed = rename_columns(df)
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            if col not in renamed.columns:
                logger.warning("Missing column %s, skipping", col)
                return pd.DataFrame()

        df = normalize_to_canonical(df, symbol, exchange)

        return df

    def merge_live_bar(self, bar: Any, df: pd.DataFrame) -> WriteResult:
        """Merge one live aggregated bar into hive-partitioned parquet.

        Used by :mod:`datalake.ingestion.live_bar_sink` (MD-001 increment 2).
        """
        if df.empty:
            return WriteResult(0, 0, 0, None, None)
        return self._write_parquet(df, bar.symbol, bar.timeframe)

    def _write_parquet(self, df: pd.DataFrame, symbol: str, timeframe: str) -> WriteResult:
        """Write DataFrame to hive-partitioned Parquet, merging with any
        existing data instead of overwriting it.

        repair_missing() writes incremental windows (e.g. a few days) that
        are shorter than the full history already on disk (e.g. 5+ years)
        -- a blind overwrite here
        would silently truncate the file to just the incremental window.
        Mirrors sync_options.py's read-merge-dedupe-write pattern.
        """
        target = self._parquet_path(symbol, timeframe)

        from datalake.quality.contract import validate_at_ingest
        from infrastructure.io.parquet import file_lock

        invalid_count = 0
        len(df)
        df, audit = validate_at_ingest(df, symbol=symbol, timeframe=timeframe, drop_invalid=True)
        invalid_count = audit.dropped_rows
        fetched_rows = len(df)

        import time

        t0 = time.perf_counter()
        with file_lock(target):
            merged = df
            if target.exists():
                try:
                    existing = pd.read_parquet(target)
                except Exception as exc:
                    logger.warning("%s: could not read existing parquet for merge: %s", symbol, exc)
                    existing = pd.DataFrame()
                if not existing.empty:
                    merged = pd.concat([existing, df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
            merged = merged.sort_values("timestamp").reset_index(drop=True)

            table = pa.Table.from_pandas(merged, preserve_index=False)
            table = enforce_canonical_schema(table)
            atomic_parquet_write(target, table, compression="snappy")

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "parquet_merge_write_ms",
            extra={"symbol": symbol, "timeframe": timeframe, "elapsed_ms": round(elapsed_ms, 2)},
        )

        if merged.empty:
            first_ts = last_ts = None
        else:
            ts = pd.to_datetime(merged["timestamp"])
            first_ts, last_ts = ts.min(), ts.max()
        return WriteResult(
            rows=fetched_rows,
            invalid_dropped=invalid_count,
            total_rows=len(merged),
            first_ts=first_ts,
            last_ts=last_ts,
        )

    def _parquet_path(self, symbol: str, timeframe: str = "1m") -> Path:
        return symbol_partition_path(
            str(self._root), normalize_symbol_for_storage(symbol), timeframe
        )

    def _check_intraday_completeness(self, df: pd.DataFrame, timeframe: str) -> float:
        """Check intraday data completeness.

        Returns
        -------
        float
            Completeness ratio (0.0 to 1.0) based on expected candles per day.
        """
        if df.empty or "timestamp" not in df.columns:
            return 0.0

        expected_per_day = expected_candles_per_day(timeframe)

        # Group by date and count candles
        ts = pd.to_datetime(df["timestamp"])
        daily_counts = ts.groupby(ts.dt.date).count()

        if len(daily_counts) == 0:
            return 0.0

        # Calculate average completeness
        avg_candles = daily_counts.mean()
        completeness = min(avg_candles / expected_per_day, 1.0)

        return completeness
