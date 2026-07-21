"""BatchQuoteCoordinator — federated multi-broker batch quote fetching.

Mirrors ``HistoricalDataCoordinator``'s shape (plan → concurrent fetch with
quota gating → merge → provenance) but simpler: a batch-quote chunk is a
*set* of symbols assigned to exactly one broker, not an overlapping date
range, so there is no conflict resolution — merging is a plain union keyed
by instrument.

Federation only kicks in when it helps: if the request fits within the
primary broker's own ``max_batch_size``, it is served by a single chunk.
Otherwise instruments are greedily packed into per-broker chunks respecting
each broker's ``max_batch_size`` and fetched concurrently.

Architecture invariant: the coordinator calls
``CommonBrokerGateway.get_quotes_batch()`` on individual gateways, mirroring
how ``HistoricalDataCoordinator`` only calls ``get_historical_bars()``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from domain.candles.historical import InstrumentRef
from domain.entities import Quote
from domain.exceptions import RoutingError
from domain.models.routing import OperationKind, RoutingRequest
from domain.ports.broker_gateway import QuotaToken
from domain.ports.time_service import get_current_clock

# ---------------------------------------------------------------------------
# Provenance — dedicated, symbol-count-shaped (not historical's date-range
# ChunkRecord, which doesn't fit a batch-quote chunk).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuoteChunkRecord:
    """Audit record for a single fetched batch-quote chunk."""

    chunk_id: str
    broker_id: str
    instrument_count: int
    error: str | None = None
    fetch_latency_ms: float = 0.0
    fetched_at: datetime = field(default_factory=lambda: get_current_clock().now())

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class QuoteProvenanceLedger:
    """Audit trail for one federated batch-quote fetch."""

    request_id: str
    chunks: list[QuoteChunkRecord] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: str = ""

    def record(self, chunk: QuoteChunkRecord) -> None:
        self.chunks.append(chunk)

    def brokers_used(self) -> set[str]:
        return {c.broker_id for c in self.chunks if c.succeeded}

    def failed_chunks(self) -> list[QuoteChunkRecord]:
        return [c for c in self.chunks if not c.succeeded]

    def mark_degraded(self, reason: str) -> None:
        self.degraded = True
        self.degraded_reason = reason


@dataclass(frozen=True)
class _QuoteChunkPlan:
    chunk_id: str
    broker_id: str
    instruments: tuple[InstrumentRef, ...]
    request_id: str
    is_fallback: bool = False


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchQuoteQuery:
    """Top-level query into the BatchQuoteCoordinator.

    instruments            — instruments to fetch quotes for.
    request_id              — caller-supplied correlation ID; generated if None.
    max_concurrent_fetches — cap on simultaneous broker calls.
    """

    instruments: tuple[InstrumentRef, ...]
    request_id: str | None = None
    max_concurrent_fetches: int = 4

    def __post_init__(self) -> None:
        if not isinstance(self.instruments, tuple):
            object.__setattr__(self, "instruments", tuple(self.instruments))


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class BatchQuoteCoordinator:
    """Federated multi-broker batch-quote coordinator.

    Usage::

        coordinator = BatchQuoteCoordinator(registry=registry, router=router,
                                             quota_fn=scheduler.acquire)
        quotes, ledger = await coordinator.fetch(query)
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

    async def fetch(
        self,
        query: BatchQuoteQuery,
    ) -> tuple[dict[InstrumentRef, Quote | None], QuoteProvenanceLedger]:
        """Fetch quotes for every instrument, federating across brokers when
        the request exceeds a single broker's batch capacity.

        Always returns a result keyed by every requested instrument (``None``
        for instruments that could not be resolved on any broker) rather than
        raising — degraded mode, same contract as ``HistoricalDataCoordinator``.
        """
        request_id = query.request_id or str(uuid.uuid4())
        ledger = QuoteProvenanceLedger(request_id=request_id)

        if not query.instruments:
            return {}, ledger

        chunks = self._plan_chunks(query.instruments, request_id)
        if not chunks:
            ledger.mark_degraded("no_chunks_planned")
            return {i: None for i in query.instruments}, ledger

        semaphore = asyncio.Semaphore(query.max_concurrent_fetches)
        fetch_results: list[
            tuple[_QuoteChunkPlan, list[Quote | None] | None]
        ] = await asyncio.gather(
            *[self._fetch_chunk_guarded(chunk, semaphore, ledger) for chunk in chunks],
            return_exceptions=False,
        )

        results: dict[InstrumentRef, Quote | None] = {}
        for plan, quotes in fetch_results:
            if quotes is None:
                quotes = await self._try_fallback(plan, ledger)
            if quotes is not None:
                for instrument, quote in zip(plan.instruments, quotes, strict=True):
                    results[instrument] = quote
            else:
                for instrument in plan.instruments:
                    results[instrument] = None

        ordered = {i: results.get(i) for i in query.instruments}
        unresolved = [i for i, q in ordered.items() if q is None]
        if unresolved:
            ledger.mark_degraded(f"{len(unresolved)}_instruments_unresolved")

        return ordered, ledger

    def fetch_sync(
        self, query: BatchQuoteQuery
    ) -> tuple[dict[InstrumentRef, Quote | None], QuoteProvenanceLedger]:
        """Synchronous wrapper around :meth:`fetch` for non-async callers."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError("fetch_sync must be called from a non-async context")
        return asyncio.run(self.fetch(query))

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _max_batch_size(self, broker_id: str) -> int:
        try:
            return max(1, self._registry.get_capabilities(broker_id).capabilities.max_batch_size)
        except Exception:
            return 1

    def _plan_chunks(
        self, instruments: tuple[InstrumentRef, ...], request_id: str
    ) -> list[_QuoteChunkPlan]:
        route_request = RoutingRequest(
            operation=OperationKind.GET_QUOTES_BATCH, trace_id=request_id
        )
        try:
            decision = self._router.route(route_request)
        except RoutingError:
            return []

        primary_cap = self._max_batch_size(decision.primary_broker)
        if len(instruments) <= primary_cap:
            # Fits in one broker — federation would only add overhead.
            return [
                _QuoteChunkPlan(
                    chunk_id=str(uuid.uuid4()),
                    broker_id=decision.primary_broker,
                    instruments=instruments,
                    request_id=request_id,
                )
            ]

        brokers = [decision.primary_broker]
        brokers.extend(b for b in decision.parallel_brokers if b not in brokers)
        brokers.extend(b for b in decision.fallback_brokers if b not in brokers)

        chunks: list[_QuoteChunkPlan] = []
        remaining = list(instruments)
        for broker_id in brokers:
            if not remaining:
                break
            cap = self._max_batch_size(broker_id)
            take, remaining = remaining[:cap], remaining[cap:]
            if take:
                chunks.append(
                    _QuoteChunkPlan(
                        chunk_id=str(uuid.uuid4()),
                        broker_id=broker_id,
                        instruments=tuple(take),
                        request_id=request_id,
                        is_fallback=broker_id != decision.primary_broker
                        and broker_id not in decision.parallel_brokers,
                    )
                )
        # Any instruments beyond combined broker capacity are left unassigned
        # — they surface as unresolved (None) in the final result.
        return chunks

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _fetch_chunk_guarded(
        self,
        plan: _QuoteChunkPlan,
        semaphore: asyncio.Semaphore,
        ledger: QuoteProvenanceLedger,
    ) -> tuple[_QuoteChunkPlan, list[Quote | None] | None]:
        async with semaphore:
            return await self._fetch_chunk(plan, ledger)

    async def _fetch_chunk(
        self,
        plan: _QuoteChunkPlan,
        ledger: QuoteProvenanceLedger,
    ) -> tuple[_QuoteChunkPlan, list[Quote | None] | None]:
        start = time.monotonic()
        try:
            quota = self._quota_fn(plan.broker_id, "quotes", "PORTFOLIO_READ")
            gw = self._registry.get_gateway(plan.broker_id)
            quotes = await gw.get_quotes_batch(list(plan.instruments), quota=quota)
            elapsed = (time.monotonic() - start) * 1000
            ledger.record(
                QuoteChunkRecord(
                    chunk_id=plan.chunk_id,
                    broker_id=plan.broker_id,
                    instrument_count=len(plan.instruments),
                    fetch_latency_ms=elapsed,
                )
            )
            return plan, list(quotes)
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            ledger.record(
                QuoteChunkRecord(
                    chunk_id=plan.chunk_id,
                    broker_id=plan.broker_id,
                    instrument_count=len(plan.instruments),
                    error=str(exc),
                    fetch_latency_ms=elapsed,
                )
            )
            return plan, None

    async def _try_fallback(
        self,
        failed_plan: _QuoteChunkPlan,
        ledger: QuoteProvenanceLedger,
    ) -> list[Quote | None] | None:
        """Try remaining eligible brokers for a failed chunk.

        Sub-splits the failed chunk if the fallback broker's own
        ``max_batch_size`` is smaller than the chunk that failed.
        """
        route_request = RoutingRequest(
            operation=OperationKind.GET_QUOTES_BATCH, trace_id=failed_plan.request_id
        )
        try:
            decision = self._router.route(route_request)
        except RoutingError:
            return None

        candidates = [
            *decision.parallel_brokers,
            decision.primary_broker,
            *decision.fallback_brokers,
        ]
        seen: set[str] = {failed_plan.broker_id}
        for broker_id in candidates:
            if broker_id in seen:
                continue
            seen.add(broker_id)

            cap = self._max_batch_size(broker_id)
            groups = [
                failed_plan.instruments[i : i + cap]
                for i in range(0, len(failed_plan.instruments), cap)
            ]
            sub_results: list[Quote | None] = []
            all_ok = True
            for group in groups:
                sub_plan = _QuoteChunkPlan(
                    chunk_id=str(uuid.uuid4()),
                    broker_id=broker_id,
                    instruments=group,
                    request_id=failed_plan.request_id,
                    is_fallback=True,
                )
                _, quotes = await self._fetch_chunk(sub_plan, ledger)
                if quotes is None:
                    all_ok = False
                    break
                sub_results.extend(quotes)
            if all_ok:
                return sub_results
        return None
