"""HistoricalDataCoordinator — federated multi-broker historical data fetching.

This is a standalone component — not embedded in any gateway.  It owns:
  - Request planning and date-range clipping per broker constraints
  - Chunk allocation across brokers based on policy and quota headroom
  - Concurrent broker fetches with quota gating
  - Bar normalization and sorting
  - Overlap validation between overlapping source windows
  - Merge with configurable conflict resolution
  - Provenance ledger construction
  - Degraded-mode fallback when a source is incomplete

The system gets historical data faster by using both brokers' quotas in
parallel where the date range can be partitioned cleanly.

Architecture invariant: the coordinator calls ``BrokerAdapter.get_historical_bars()``
on individual gateways.  It does not call gateway.history() or any internal
adapter method.  Provenance survives every step.

The heavy lifting is delegated to focused collaborators:
  - :class:`ChunkPlanner`   — chunk planning and range partitioning
  - :class:`ChunkMerger`     — chunk result recording, merge, bar ranges
  - :class:`GapDetector`     — gap detection and empty-series construction

Usage Example:
    # Create coordinator with broker registry and router
    coordinator = HistoricalDataCoordinator(
        registry=BrokerRegistry(),
        router=BrokerRouter(),
        policy=default_source_selection_policy(),
    )

    # Create and execute query
    query = HistoricalQuery(
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        timeframe="1D",
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
        merge_strategy="prefer_primary",
    )

    # Get historical bars (automatically federates across brokers)
    bars = coordinator.get_historical_bars(query)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal

from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from application.data.chunk_merger import ChunkMerger, MergeStrategy
from application.data.chunk_planner import ChunkPlan, ChunkPlanner
from application.data.gap_detector import GapDetector
from application.data.provenance import ProvenanceLedger
from domain.candles.historical import (
    DateRange,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
    MergeManifest,
)
from domain.errors import MergeConflictError, RoutingError
from domain.models.routing import OperationKind, RouteDecision, RoutingRequest
from domain.ports.broker_gateway import (
    HistoricalBarRequest,
    QuotaToken,
)
from domain.ports.audit import emit_historical_chunk

logger = logging.getLogger(__name__)

# Backward-compatible alias for the (private) planning record.
_ChunkPlan = ChunkPlan

# Tolerance for OHLCV comparison between overlapping sources (10 basis points)
_DEFAULT_CONFLICT_TOLERANCE_PCT = Decimal("0.001")


@dataclass(frozen=True)
class HistoricalQuery:
    """Top-level query into the HistoricalDataCoordinator.

    instrument      — the instrument to fetch.
    timeframe       — candle interval, e.g. ``"1m"``, ``"1D"``.
    from_date       — requested start date (inclusive).
    to_date         — requested end date (inclusive).
    merge_strategy  — how to resolve conflicts when sources overlap.
    conflict_tolerance_pct — relative tolerance for OHLCV comparison.
    request_id      — caller-supplied correlation ID; one is generated if None.
    max_concurrent_fetches — cap on simultaneous broker calls.
    """

    instrument: InstrumentRef
    timeframe: str
    from_date: date
    to_date: date
    merge_strategy: MergeStrategy = "prefer_primary"
    conflict_tolerance_pct: Decimal = _DEFAULT_CONFLICT_TOLERANCE_PCT
    request_id: str | None = None
    max_concurrent_fetches: int = 4


class HistoricalDataCoordinator:
    """Federated multi-broker historical data coordinator.

    Usage::

        coordinator = HistoricalDataCoordinator(registry=registry, router=router,
                                                 quota_fn=scheduler.acquire)
        series, ledger = await coordinator.fetch(query)
    """

    def __init__(
        self,
        registry: BrokerRegistry,
        router: BrokerRouter,
        quota_fn: Callable[[str, str, str], QuotaToken],
    ) -> None:
        """
        quota_fn
            Callable ``(broker_id, endpoint_class, priority_class) -> QuotaToken``.
            Typically ``QuotaScheduler.acquire``.
        """
        self._registry = registry
        self._router = router
        self._quota_fn = quota_fn
        self._planner = ChunkPlanner(registry=registry, router=router)
        self._gap_detector = GapDetector()

    async def fetch(
        self,
        query: HistoricalQuery,
    ) -> tuple[HistoricalSeries, ProvenanceLedger]:
        """Fetch, normalize, validate, and merge historical bars.

        Returns the merged ``HistoricalSeries`` and its ``ProvenanceLedger``.
        Always returns a result — uses degraded mode rather than raising when
        a source is partially unavailable.

        Raises
        ------
        RoutingError      — if no broker can be selected for any chunk.
        MergeConflictError — if ``merge_strategy="fail_on_conflict"`` and
                             irreconcilable conflicts are detected.
        """
        request_id = query.request_id or str(uuid.uuid4())
        ledger = ProvenanceLedger(
            request_id=request_id,
            instrument=str(query.instrument),
            timeframe=query.timeframe,
            merge_strategy=query.merge_strategy,
        )

        # 1. Plan chunks
        chunks = self._plan_chunks(query, request_id)
        if not chunks:
            # Build empty degraded series
            ledger.mark_degraded("no_chunks_planned")
            return self._empty_series(query, ledger), ledger

        # 2. Fetch all chunks concurrently (respecting concurrency cap)
        semaphore = asyncio.Semaphore(query.max_concurrent_fetches)
        fetch_results: list[
            tuple[ChunkPlan, Sequence[HistoricalBar] | None]
        ] = await asyncio.gather(
            *[self._fetch_chunk_guarded(chunk, semaphore, ledger) for chunk in chunks],
            return_exceptions=False,
        )

        # 3. Collect bars per chunk
        all_bars: list[HistoricalBar] = []
        chunk_bars: dict[str, list[HistoricalBar]] = {}
        for plan, bars in fetch_results:
            if not bars:
                # Empty result (broker returned zero bars, no error) is
                # indistinguishable from "not published yet" -- try the
                # fallback broker rather than accepting it as a real gap.
                bars = await self._try_fallback(plan, ledger)
            if bars is not None:
                chunk_bars[plan.chunk_id] = list(bars)
                all_bars.extend(bars)

        if not all_bars:
            ledger.mark_degraded("all_chunks_failed")
            return self._empty_series(query, ledger), ledger

        # 4-7. Sort, merge, reindex, detect gaps
        merged, gaps = self._merge_and_detect_gaps(
            all_bars, chunk_bars, chunks, query, ledger, request_id
        )

        # 7b. A chunk can "succeed" (non-empty) while still landing short of
        # the requested range -- e.g. a broker silently drops today's
        # in-progress session from an otherwise-valid multi-day response.
        # GapDetector already catches this (missing_from_start/end/chunk);
        # previously nothing acted on it. Try one broker that hasn't
        # contributed to this request yet, per gap, before finalizing.
        if gaps:
            tried_brokers = {c.broker_id for c in ledger.chunks}
            gap_bars = await self._fill_gaps(gaps, query, request_id, tried_brokers, ledger)
            if gap_bars:
                all_bars.extend(gap_bars)
                merged, gaps = self._merge_and_detect_gaps(
                    all_bars, chunk_bars, chunks, query, ledger, request_id
                )

        # 8. Build merge manifest
        all_failed = ledger.failed_chunks()
        manifest = MergeManifest(
            chunk_assignments={p.chunk_id: p.broker_id for p in chunks},
            conflict_count=len(ledger.conflicts),
            conflict_resolution=query.merge_strategy,
            degraded=len(all_failed) > 0,
            degraded_reason="; ".join(f.error or "" for f in all_failed if f.error),
        )
        if manifest.degraded:
            ledger.mark_degraded(manifest.degraded_reason)

        series = HistoricalSeries(
            bars=merged,
            coverage=DateRange(start=query.from_date, end=query.to_date),
            instrument=query.instrument,
            timeframe=query.timeframe,
            gaps=gaps,
            merge_manifest=manifest,
        )

        logger.info(
            "historical.fetch.complete",
            extra={
                **ledger.to_summary_dict(),
                "gaps_count": len(gaps),
            },
        )
        return series, ledger

    def fetch_sync(self, query: HistoricalQuery) -> tuple[HistoricalSeries, ProvenanceLedger]:
        """Synchronous wrapper around :meth:`fetch` for non-async callers.

        Used by the ``brokers`` layer (``BrokerSession.history``) which is
        sync-only. Wraps ``asyncio.run``; fails fast if called from inside a
        running event loop rather than silently misbehaving.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError("fetch_sync must be called from a non-async context")
        return asyncio.run(self.fetch(query))

    # ------------------------------------------------------------------
    # Planning (delegated to ChunkPlanner)
    # ------------------------------------------------------------------

    def _plan_chunks(self, query: HistoricalQuery, request_id: str) -> list[ChunkPlan]:
        return self._planner.plan(query, request_id)

    def _partition_ranges(
        self,
        from_date: date,
        to_date: date,
        timeframe: str,
        broker_ids: list[str],
        today: date,
    ) -> dict[str, tuple[date, date]]:
        return self._planner.partition(from_date, to_date, timeframe, broker_ids, today)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _fetch_chunk_guarded(
        self,
        plan: ChunkPlan,
        semaphore: asyncio.Semaphore,
        ledger: ProvenanceLedger,
    ) -> tuple[ChunkPlan, Sequence[HistoricalBar] | None]:
        async with semaphore:
            return await self._fetch_chunk(plan, ledger)

    async def _fetch_chunk(
        self,
        plan: ChunkPlan,
        ledger: ProvenanceLedger,
    ) -> tuple[ChunkPlan, Sequence[HistoricalBar] | None]:
        import time

        start = time.monotonic()
        try:
            quota = self._quota_fn(plan.broker_id, "historical", "HISTORICAL_BACKFILL")
            gw = self._registry.get_gateway(plan.broker_id)
            request = HistoricalBarRequest(
                instrument=plan.instrument,
                timeframe=plan.timeframe,
                from_date=plan.from_date.isoformat(),
                to_date=plan.to_date.isoformat(),
                request_id=plan.request_id,
            )
            bars = await gw.get_historical_bars(request, quota=quota)
            elapsed = (time.monotonic() - start) * 1000
            self._record_chunk_result(plan, ledger, bars, elapsed)
            return plan, bars
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_chunk_result(plan, ledger, None, elapsed, error=exc)
            return plan, None

    def _record_chunk_result(
        self,
        plan: ChunkPlan,
        ledger: ProvenanceLedger,
        bars: Sequence[HistoricalBar] | None,
        elapsed_ms: float,
        error: Exception | None = None,
    ) -> None:
        ChunkMerger(ledger, audit_fn=emit_historical_chunk).record(
            plan, bars, elapsed_ms, error=error
        )

    async def _try_fallback(
        self,
        failed_plan: ChunkPlan,
        ledger: ProvenanceLedger,
    ) -> Sequence[HistoricalBar] | None:
        """Try remaining eligible brokers for a failed chunk."""
        route_request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS,
            trace_id=failed_plan.request_id,
        )
        try:
            decision = self._router.route(route_request)
        except RoutingError:
            return None

        # Quota-aware scoring is dynamic -- a second route() call here can
        # re-rank brokers and swap primary/fallback vs. the original plan.
        # Filtering decision.fallback_brokers alone can then wipe out the
        # only real alternative (e.g. it re-ranks the failed broker back
        # into "fallback_brokers"). Use the full eligible set instead so
        # any broker other than the one that just failed still gets tried.
        eligible = decision.parallel_brokers or (
            decision.primary_broker,
            *decision.fallback_brokers,
        )
        fallbacks = [b for b in eligible if b != failed_plan.broker_id]
        for fallback_id in fallbacks:
            fallback_plan = ChunkPlan(
                chunk_id=str(uuid.uuid4()),
                broker_id=fallback_id,
                instrument=failed_plan.instrument,
                from_date=failed_plan.from_date,
                to_date=failed_plan.to_date,
                timeframe=failed_plan.timeframe,
                request_id=failed_plan.request_id,
                is_fallback=True,
            )
            _, bars = await self._fetch_chunk(fallback_plan, ledger)
            if bars is not None:
                # Mark bars as fallback provenance
                fallback_bars = [
                    HistoricalBar(
                        instrument=b.instrument,
                        timeframe=b.timeframe,
                        event_time=b.event_time,
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        volume=b.volume,
                        open_interest=b.open_interest,
                        bar_index=b.bar_index,
                        is_partial=b.is_partial,
                        label_convention=b.label_convention,
                        provenance=b.provenance.as_fallback(),
                    )
                    for b in bars
                ]
                return fallback_bars
        return None

    async def _fill_gaps(
        self,
        gaps: list,
        query: HistoricalQuery,
        request_id: str,
        tried_brokers: set[str],
        ledger: ProvenanceLedger,
    ) -> list[HistoricalBar]:
        """Try one not-yet-tried broker per gap range before giving up on it.

        Only called when :class:`GapDetector` found a hole in coverage after
        merge -- i.e. every chunk "succeeded" (non-empty) but the result is
        still short of the requested range. Uses ``parallel_brokers`` (the
        full eligible set) rather than ``fallback_brokers``: quota-aware
        scoring is time-varying (see ``_try_fallback``), so re-deriving
        "the other broker(s)" from a fresh route() call and filtering out
        already-tried ones is safer than trusting that call's own
        primary/fallback split.
        """
        route_request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS, trace_id=request_id
        )
        try:
            decision = self._router.route(route_request)
        except RoutingError:
            return []

        eligible = decision.parallel_brokers or (
            decision.primary_broker,
            *decision.fallback_brokers,
        )
        candidates = [b for b in eligible if b not in tried_brokers]
        if not candidates:
            return []

        filled: list[HistoricalBar] = []
        for gap in gaps:
            for broker_id in candidates:
                plan = ChunkPlan(
                    chunk_id=str(uuid.uuid4()),
                    broker_id=broker_id,
                    instrument=query.instrument,
                    from_date=gap.start,
                    to_date=gap.end,
                    timeframe=query.timeframe,
                    request_id=request_id,
                    is_fallback=True,
                )
                _, bars = await self._fetch_chunk(plan, ledger)
                if bars:
                    filled.extend(bars)
                    break
        return filled

    # ------------------------------------------------------------------
    # Merge (delegated to ChunkMerger)
    # ------------------------------------------------------------------

    def _merge_and_detect_gaps(
        self,
        all_bars: list[HistoricalBar],
        chunk_bars: dict[str, list[HistoricalBar]],
        chunks: list[ChunkPlan],
        query: HistoricalQuery,
        ledger: ProvenanceLedger,
        request_id: str,
    ) -> tuple[list[HistoricalBar], list]:
        all_bars = sorted(all_bars, key=lambda b: b.event_time)

        merged, conflicts = self._merge(
            all_bars,
            chunk_bars=chunk_bars,
            strategy=query.merge_strategy,
            tolerance=query.conflict_tolerance_pct,
            ledger=ledger,
        )
        for c in conflicts:
            ledger.add_conflict(c)
            with contextlib.suppress(Exception):
                from domain.ports.audit import emit_merge_conflict

                emit_merge_conflict(
                    request_id=request_id,
                    instrument=c.instrument,
                    timeframe=c.timeframe,
                    bar_event_time=c.bar_event_time.isoformat(),
                    primary_broker=c.primary_broker,
                    secondary_broker=c.secondary_broker,
                    delta_pct=str(c.delta_pct),
                    resolution=c.resolution,
                )

        if query.merge_strategy == "fail_on_conflict" and conflicts:
            raise MergeConflictError(
                conflict_count=len(conflicts),
                chunk_ids=list(chunk_bars.keys()),
            )

        merged = [replace(bar, bar_index=idx) for idx, bar in enumerate(merged)]
        self._populate_bar_ranges(merged, ledger)
        gaps = self._detect_gaps(merged, query, planned_chunks=chunks)
        return merged, gaps

    def _merge(
        self,
        bars: list[HistoricalBar],
        chunk_bars: dict[str, list[HistoricalBar]],
        strategy: MergeStrategy,
        tolerance: Decimal,
        ledger: ProvenanceLedger | None = None,
    ) -> tuple[list[HistoricalBar], list]:
        return ChunkMerger(
            ledger or ProvenanceLedger(request_id="", instrument="", timeframe="")
        ).merge(bars, chunk_bars=chunk_bars, strategy=strategy, tolerance=tolerance)

    def _populate_bar_ranges(
        self,
        bars: list[HistoricalBar],
        ledger: ProvenanceLedger,
    ) -> None:
        ChunkMerger(ledger).populate_bar_ranges(bars)

    # ------------------------------------------------------------------
    # Gap detection (delegated to GapDetector)
    # ------------------------------------------------------------------

    def _detect_gaps(
        self,
        bars: list[HistoricalBar],
        query: HistoricalQuery,
        planned_chunks: list | None = None,
    ) -> list:
        return self._gap_detector.detect(bars, query, planned_chunks=planned_chunks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_series(query: HistoricalQuery, ledger: ProvenanceLedger) -> HistoricalSeries:
        return GapDetector.empty_series(query, ledger)
