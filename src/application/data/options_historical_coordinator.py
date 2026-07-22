"""Federated options historical coordinator — Dhan-primary rolling fetch."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd

from application.data.dhan_rolling_options_fetcher import DhanRollingOptionsFetcher
from application.data.provenance import ChunkRecord, ProvenanceLedger
from domain.candles.options_historical import OptionsHistoricalQuery
from infrastructure.batch_executor import batch_execute

logger = logging.getLogger(__name__)

_MAX_CHUNK_DAYS = 30


def _date_chunks(from_date: date, to_date: date, max_days: int) -> list[tuple[date, date]]:
    if from_date > to_date:
        return []
    chunks: list[tuple[date, date]] = []
    cur = from_date
    while cur <= to_date:
        end = min(cur + timedelta(days=max_days - 1), to_date)
        chunks.append((cur, end))
        cur = end + timedelta(days=1)
    return chunks


class OptionsHistoricalCoordinator:
    """Plan and fetch rolling options bars for one lake partition group."""

    def __init__(
        self,
        fetcher: DhanRollingOptionsFetcher,
        *,
        max_chunk_days: int = _MAX_CHUNK_DAYS,
        max_workers: int = 1,
    ) -> None:
        self._fetcher = fetcher
        self._max_chunk_days = max_chunk_days
        self._max_workers = max_workers

    def fetch(self, query: OptionsHistoricalQuery) -> tuple[pd.DataFrame, ProvenanceLedger]:
        """Fetch all strike/side series for the query date range (sync)."""
        request_id = query.request_id or str(uuid.uuid4())
        ledger = ProvenanceLedger(
            request_id=request_id,
            instrument=str(query.underlying),
            timeframe=f"{query.interval_min}m",
        )
        frames: list[pd.DataFrame] = []
        errors: list[str] = []

        for chunk_from, chunk_to in _date_chunks(query.from_date, query.to_date, self._max_chunk_days):
            from_s = chunk_from.isoformat()
            to_s = chunk_to.isoformat()
            chunk_errors: list[str] = []
            work_keys = [
                f"{offset}:{ot}"
                for offset in query.strike_offsets
                for ot in query.option_types
            ]

            def _fetch_one(key: str) -> pd.DataFrame:
                offset_s, ot = key.split(":", 1)
                return self._fetcher.fetch_series(
                    underlying=query.underlying,
                    expiry_kind=query.expiry_kind,
                    expiry_code=query.expiry_code,
                    strike_offset=int(offset_s),
                    option_type=ot,  # type: ignore[arg-type]
                    from_date=from_s,
                    to_date=to_s,
                    interval_min=query.interval_min,
                )

            def _on_error(key: str, exc: Exception) -> None:
                msg = f"{key}@{from_s}:{to_s}: {exc}"
                chunk_errors.append(msg)
                errors.append(msg)
                logger.warning("options_fetch_failed %s", msg)

            results = batch_execute(
                work_keys,
                _fetch_one,
                max_workers=self._max_workers,
                on_error=_on_error,
            )
            bars_fetched = sum(len(df) for df in results.values())
            chunk_id = f"{request_id}:{from_s}:{to_s}"
            ledger.add_chunk(
                ChunkRecord(
                    chunk_id=chunk_id,
                    broker_id=self._fetcher._broker_id,
                    from_date=chunk_from,
                    to_date=chunk_to,
                    timeframe=f"{query.interval_min}m",
                    bars_fetched=bars_fetched,
                    error="; ".join(chunk_errors[-5:]) if chunk_errors else None,
                )
            )
            frames.extend(results.values())

        if errors:
            ledger.mark_degraded(f"{len(errors)} contract fetch failures")

        if not frames:
            return pd.DataFrame(), ledger

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
        combined = combined.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
        return combined, ledger


def require_complete_options_fetch(
    underlying: str,
    ek: str,
    ec: int,
    ledger: ProvenanceLedger,
) -> None:
    """Fail closed when federation returned partial/degraded options data."""
    if ledger.degraded:
        raise RuntimeError(
            f"[{underlying} {ek} {ec}] options fetch degraded: {ledger.degraded_reason}"
        )
