"""ReplayDataLoader — bar + event data loading for unified replay.

Extracts the data-loading responsibility from ``UnifiedReplayOrchestrator``.
Loads OHLCV bars from the datalake (via an injected data provider) and domain
events from the EventLog, returning both as ``ReplayItem`` streams.

Dependencies are injected via the constructor so the loader has no circular
dependency on the orchestrator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from analytics.replay.models import ReplayItem
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)


class ReplayDataLoader:
    """Loads bars and events as ``ReplayItem`` streams for replay.

    Parameters
    ----------
    data_provider:
        Injected data provider (DataLakeGateway, ResearchAPI, …). If None, a
        ``DataLakeMarketDataProvider`` is lazily created from ``data_root``.
    event_log:
        EventLog used to read persisted domain events. May be None.
    data_root:
        Root path for the datalake.
    timeframe:
        Candle timeframe (default ``1m``).
    """

    def __init__(
        self,
        data_provider: Any | None = None,
        event_log: Any | None = None,
        data_root: str = DEFAULT_DATA_ROOT,
        timeframe: str = "1m",
    ) -> None:
        self._data_provider = data_provider
        self._event_log = event_log
        self._data_root = data_root
        self._timeframe = timeframe

    def load_bars(self, date: str, symbols: list[str]) -> list[ReplayItem]:
        """Load OHLCV bars from the datalake for the target date."""
        if self._data_provider is None:
            from datalake.adapters.analytics_provider import DataLakeMarketDataProvider

            data_provider = DataLakeMarketDataProvider(root=self._data_root)
        else:
            data_provider = self._data_provider

        items: list[ReplayItem] = []
        seq = 0

        if symbols:
            for sym in symbols:
                try:
                    df = data_provider.history(
                        sym,
                        timeframe=self._timeframe,
                        from_date=date,
                        to_date=date,
                    )
                    if df.empty:
                        continue
                    items.extend(self.df_to_items(df, sym, seq_start=seq))
                    seq += len(df)
                except Exception as exc:
                    logger.warning(
                        "Failed to load bars for %s on %s: %s",
                        sym,
                        date,
                        exc,
                    )
        else:
            logger.warning(
                "No symbols specified for replay. Provide symbols list for deterministic replay."
            )

        return items

    def df_to_items(
        self, df: pd.DataFrame, symbol: str, seq_start: int = 0
    ) -> list[ReplayItem]:
        """Convert a DataFrame of OHLCV data to ReplayItems (vectorized)."""
        ts_col = "timestamp" if "timestamp" in df.columns else "date"
        timestamps = pd.to_datetime(df[ts_col]).dt.tz_localize(timezone.utc)

        return [
            ReplayItem(
                timestamp=ts,
                sequence=seq_start + i,
                kind="bar",
                symbol=symbol,
                bar_data={
                    "symbol": symbol,
                    "timestamp": ts,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                },
            )
            for i, (ts, row) in enumerate(
                zip(timestamps, df.itertuples(index=False), strict=False)
            )
        ]

    def load_events(
        self, day_start: datetime, day_end: datetime
    ) -> list[ReplayItem]:
        """Load domain events from the event log for the target day."""
        if self._event_log is None:
            return []

        try:
            events = self._event_log.replay(since=day_start)
            items: list[ReplayItem] = []

            for evt in events:
                if evt.timestamp > day_end:
                    break
                items.append(
                    ReplayItem(
                        timestamp=evt.timestamp,
                        sequence=evt.sequence_number,
                        kind="event",
                        symbol=evt.symbol,
                        event=evt,
                    )
                )

            logger.info("Loaded %d events from event log", len(items))
            return items
        except Exception as exc:
            logger.warning("Failed to load events: %s", exc)
            return []
