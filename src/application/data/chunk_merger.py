"""Chunk result recording and series merging for the historical coordinator.

This module is intentionally free of any import from
``application.data.historical_coordinator`` to avoid a circular dependency.
``ChunkPlan`` is referenced only under ``TYPE_CHECKING`` (it lives in
``chunk_planner``); ``MergeStrategy`` is defined here and re-imported by the
coordinator.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from application.data.provenance import (
    BarRangeRecord,
    ChunkRecord,
    ConflictRecord,
    ProvenanceLedger,
)
from domain.candles.historical import HistoricalBar, HistoricalSeries

if TYPE_CHECKING:
    from application.data.chunk_planner import ChunkPlan

logger = logging.getLogger(__name__)

MergeStrategy = Literal["prefer_primary", "prefer_newest_provenance", "fail_on_conflict"]

AuditFn = Callable[..., None]


class ChunkMerger:
    """Record chunk outcomes and merge bars into a final series."""

    def __init__(
        self,
        ledger: ProvenanceLedger,
        *,
        audit_fn: AuditFn | None = None,
    ) -> None:
        self._ledger = ledger
        self._audit_fn = audit_fn

    def record(
        self,
        plan: ChunkPlan,
        bars: Sequence[HistoricalBar] | None,
        elapsed_ms: float,
        error: Exception | None = None,
    ) -> None:
        """Record chunk outcome in the ledger, audit log, and structured log."""
        bar_count = len(bars) if bars is not None else 0
        event_type = "complete" if error is None else "failed"

        self._ledger.add_chunk(
            ChunkRecord(
                chunk_id=plan.chunk_id,
                broker_id=plan.broker_id,
                from_date=plan.from_date,
                to_date=plan.to_date,
                timeframe=plan.timeframe,
                bars_fetched=bar_count,
                error=str(error) if error else None,
                fetch_latency_ms=elapsed_ms,
            )
        )

        if self._audit_fn is not None:
            self._audit_fn(
                request_id=plan.request_id,
                chunk_id=plan.chunk_id,
                broker_id=plan.broker_id,
                from_date=plan.from_date.isoformat(),
                to_date=plan.to_date.isoformat(),
                timeframe=plan.timeframe,
                event_type=event_type,
                bar_count=bar_count,
                latency_ms=elapsed_ms,
                **({"error": str(error)} if error else {}),
            )

        if error is None:
            logger.info(
                "historical.chunk.complete",
                extra={
                    "chunk_id": plan.chunk_id,
                    "broker_id": plan.broker_id,
                    "from_date": plan.from_date.isoformat(),
                    "to_date": plan.to_date.isoformat(),
                    "bar_count": bar_count,
                    "request_id": plan.request_id,
                },
            )
        else:
            logger.warning(
                "historical.chunk.failed",
                extra={
                    "chunk_id": plan.chunk_id,
                    "broker_id": plan.broker_id,
                    "error": str(error),
                    "request_id": plan.request_id,
                },
            )

    def merge(
        self,
        bars: list[HistoricalBar],
        chunk_bars: dict[str, list[HistoricalBar]],
        strategy: MergeStrategy,
        tolerance: Decimal,
    ) -> tuple[list[HistoricalBar], list[ConflictRecord]]:
        """Merge sorted bars, detecting and resolving OHLCV conflicts."""
        conflicts: list[ConflictRecord] = []
        merged: dict[datetime, HistoricalBar] = {}

        for bar in bars:
            ts = bar.event_time
            if ts not in merged:
                merged[ts] = bar
                continue

            existing = merged[ts]
            delta = abs(bar.close - existing.close)
            base = existing.close if existing.close != Decimal("0") else Decimal("1")
            delta_pct = delta / base

            if delta_pct <= tolerance:
                # Within tolerance — prefer existing (primary source)
                continue

            # Conflict outside tolerance
            conflict = ConflictRecord(
                bar_event_time=ts,
                instrument=str(bar.instrument),
                timeframe=bar.timeframe,
                primary_broker=existing.provenance.source.broker_id,
                secondary_broker=bar.provenance.source.broker_id,
                primary_close=existing.close,
                secondary_close=bar.close,
                delta_pct=delta_pct,
                resolution=strategy,
            )
            conflicts.append(conflict)

            if strategy == "prefer_primary":
                pass  # keep existing
            elif (
                strategy == "prefer_newest_provenance"
                and bar.provenance.fetched_at > existing.provenance.fetched_at
            ):
                merged[ts] = bar
            # fail_on_conflict: keep existing; caller raises after seeing conflicts

        return sorted(merged.values(), key=lambda b: b.event_time), conflicts

    def populate_bar_ranges(self, bars: list[HistoricalBar]) -> None:
        """Build BarRangeRecord entries mapping bar indices to source chunks."""
        if not bars:
            return

        current_broker = bars[0].provenance.source.broker_id
        current_chunk_id = bars[0].provenance.request_id
        range_start = 0

        for idx in range(1, len(bars)):
            bar = bars[idx]
            broker = bar.provenance.source.broker_id
            chunk_id = bar.provenance.request_id
            if broker != current_broker or chunk_id != current_chunk_id:
                self._ledger.add_bar_range(
                    BarRangeRecord(
                        start_bar_index=range_start,
                        end_bar_index=idx - 1,
                        chunk_id=current_chunk_id,
                        broker_id=current_broker,
                    )
                )
                current_broker = broker
                current_chunk_id = chunk_id
                range_start = idx

        self._ledger.add_bar_range(
            BarRangeRecord(
                start_bar_index=range_start,
                end_bar_index=len(bars) - 1,
                chunk_id=current_chunk_id,
                broker_id=current_broker,
            )
        )
