"""Live aggregated bars → datalake parquet (MD-001 increment 2).

Completed bars are enqueued from the EventBus hot path; a single background
writer thread performs merge-write so tick subscribers never block on parquet I/O.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any

import pandas as pd

from datalake.core.symbols import normalize_symbol_for_storage
from datalake.ingestion.loader import HistoricalDataLoader, WriteResult
from datalake.ingestion.normalize import ensure_timestamp_dtype
from domain.candles.historical import HistoricalBar

logger = logging.getLogger(__name__)

_SENTINEL = object()


@dataclass(frozen=True)
class _WriteJob:
    bar: HistoricalBar
    df: pd.DataFrame


def historical_bar_to_dataframe(bar: HistoricalBar) -> pd.DataFrame:
    """Convert one :class:`HistoricalBar` to a single-row canonical DataFrame."""
    df = pd.DataFrame(
        [
            {
                "timestamp": bar.event_time,
                "symbol": normalize_symbol_for_storage(bar.symbol),
                "exchange": bar.exchange,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "oi": int(bar.open_interest),
            }
        ]
    )
    return ensure_timestamp_dtype(df)


class LiveBarSink:
    """Persist completed live candles via :class:`HistoricalDataLoader` merge-write."""

    def __init__(
        self,
        root: str | None = None,
        catalog=None,
        loader: HistoricalDataLoader | None = None,
        *,
        sync: bool | None = None,
    ) -> None:
        self._loader = loader or HistoricalDataLoader(root=root, catalog=catalog)
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=4096)
        self._sync = sync
        self._writer = threading.Thread(
            target=self._writer_loop,
            name="live-bar-sink",
            daemon=True,
        )
        self._writer.start()
        self._inflight = threading.Event()

    def write_bar(self, bar: HistoricalBar) -> WriteResult:
        """Enqueue one closed bar; returns immediately on the hot path."""
        df = historical_bar_to_dataframe(bar)
        if df.empty:
            return WriteResult(0, 0, 0, None, None)
        if self._sync:
            return self._persist(bar, df)
        job = _WriteJob(bar=bar, df=df)
        self._inflight.set()
        try:
            self._queue.put(job, block=False)
        except queue.Full:
            logger.warning(
                "live_bar_sink.queue_full symbol=%s tf=%s — dropping bar",
                bar.symbol,
                bar.timeframe,
            )
            self._inflight.clear()
            return WriteResult(0, 0, 0, None, None)
        return WriteResult(1, 0, 0, None, None)

    def flush(self, timeout: float = 30.0) -> None:
        """Drain queued writes and wait for the in-flight merge-write to finish."""
        import time

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self._queue.join()
            if not self._inflight.is_set():
                return
            time.sleep(0.01)
        logger.warning("live_bar_sink.flush timed out after %.1fs", timeout)

    def close(self) -> None:
        """Stop the background writer after draining pending jobs."""
        self.flush()
        self._queue.put(_SENTINEL)
        self._writer.join(timeout=5.0)

    def _writer_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            assert isinstance(item, _WriteJob)
            self._inflight.set()
            try:
                self._persist(item.bar, item.df)
            except Exception as exc:
                logger.warning(
                    "live_bar_sink.write_failed symbol=%s tf=%s: %s",
                    item.bar.symbol,
                    item.bar.timeframe,
                    exc,
                )
            finally:
                self._inflight.clear()
                self._queue.task_done()

    def _persist(self, bar: HistoricalBar, df: pd.DataFrame) -> WriteResult:
        result = self._loader.merge_live_bar(bar, df)
        catalog = getattr(self._loader, "_catalog", None)
        if catalog is not None and result.last_ts is not None:
            last_date = pd.Timestamp(result.last_ts).date()
            path = self._loader._parquet_path(bar.symbol, bar.timeframe)
            catalog.register_symbol(
                bar.symbol,
                exchange=bar.exchange,
                last_date=last_date,
                total_rows=result.total_rows,
                timeframe=bar.timeframe,
                parquet_path=str(path),
            )
        logger.debug(
            "live_bar_sink.wrote symbol=%s tf=%s rows=%d total=%d",
            bar.symbol,
            bar.timeframe,
            result.rows,
            result.total_rows,
        )
        return result
