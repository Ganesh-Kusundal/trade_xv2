"""Chunk planning for the historical data coordinator.

Splits a requested date range into per-broker, per-window chunks and
partitions the overall range across eligible brokers so that work is not
duplicated.

This module is intentionally free of any import from
``application.data.historical_coordinator`` to avoid a circular dependency.
``HistoricalQuery`` is referenced only in lazy type annotations (enabled by
``from __future__ import annotations``) and is never evaluated at runtime.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from domain.candles.historical import InstrumentRef
from domain.errors import RoutingError
from domain.models.routing import OperationKind, RouteDecision, RoutingRequest

logger = logging.getLogger(__name__)


@dataclass
class ChunkPlan:
    """Planning record describing one fetch chunk assigned to a broker."""

    chunk_id: str
    broker_id: str
    instrument: InstrumentRef
    from_date: date
    to_date: date
    timeframe: str
    request_id: str
    is_fallback: bool = False


class ChunkPlanner:
    """Plan fetch chunks and partition ranges across brokers."""

    def __init__(self, registry: BrokerRegistry, router: BrokerRouter) -> None:
        self._registry = registry
        self._router = router

    def plan(self, query: HistoricalQuery, request_id: str) -> list[ChunkPlan]:
        """Plan fetch chunks by clipping ranges and assigning to brokers.

        Strategy:
        1. Ask the router for parallel brokers.
        2. For each eligible broker, determine the date range it can serve
           (constrained by HistoricalWindowConstraint).
        3. Partition the requested range so brokers do not duplicate work:
           - Upstox takes the most recent window (up to its max_lookback_days).
           - Dhan takes the remainder.
        4. Split long ranges into max_chunk_days chunks.
        """
        # Determine routing
        route_request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS,
            trace_id=request_id,
            instrument=str(query.instrument),
        )
        try:
            decision: RouteDecision = self._router.route(route_request)
        except RoutingError:
            logger.error(
                "historical.routing.failed",
                extra={"request_id": request_id, "instrument": str(query.instrument)},
            )
            return []

        eligible_brokers = list(decision.parallel_brokers) or [decision.primary_broker]
        today = date.today()
        chunks: list[ChunkPlan] = []

        # Determine per-broker feasible ranges and partition
        broker_ranges = self.partition(
            query.from_date, query.to_date, query.timeframe, eligible_brokers, today
        )

        for broker_id, (from_d, to_d) in broker_ranges.items():
            cap_descriptor = self._registry.get_capabilities(broker_id)
            constraint = cap_descriptor.capabilities.historical_window_for(query.timeframe)
            max_chunk = constraint.max_chunk_days if constraint else 90

            # Split into chunks
            current = from_d
            while current <= to_d:
                end = min(current + timedelta(days=max_chunk - 1), to_d)
                chunks.append(
                    ChunkPlan(
                        chunk_id=str(uuid.uuid4()),
                        broker_id=broker_id,
                        instrument=query.instrument,
                        from_date=current,
                        to_date=end,
                        timeframe=query.timeframe,
                        request_id=request_id,
                    )
                )
                current = end + timedelta(days=1)

        return chunks

    def partition(
        self,
        from_date: date,
        to_date: date,
        timeframe: str,
        broker_ids: list[str],
        today: date,
    ) -> dict[str, tuple[date, date]]:
        """Partition the requested range across eligible brokers.

        For two brokers where one (e.g. Upstox) has a short intraday window and
        the other (Dhan) has a long one, the recent window goes to Upstox and
        the older portion goes to Dhan — avoiding duplicated fetches.
        """
        result: dict[str, tuple[date, date]] = {}

        # Build broker window map: broker_id -> max_lookback_days
        broker_windows: dict[str, int] = {}
        for bid in broker_ids:
            with contextlib.suppress(Exception):
                cap = self._registry.get_capabilities(bid).capabilities
                constraint = cap.historical_window_for(timeframe)
                if constraint and cap.supports_historical_data:
                    broker_windows[bid] = constraint.max_lookback_days

        if not broker_windows:
            return result

        if len(broker_windows) == 1:
            bid, max_days = next(iter(broker_windows.items()))
            earliest = today - timedelta(days=max_days)
            effective_from = max(from_date, earliest)
            if effective_from <= to_date:
                result[bid] = (effective_from, to_date)
            return result

        # Multi-broker: sort by coverage ascending (shorter coverage = recent window)
        sorted_brokers = sorted(broker_windows.items(), key=lambda x: x[1])
        # The broker with shorter max_lookback takes the recent slice
        short_broker, short_days = sorted_brokers[0]
        long_broker, long_days = sorted_brokers[-1]

        short_earliest = today - timedelta(days=short_days)
        long_earliest = today - timedelta(days=long_days)

        # Short broker: max(from_date, short_earliest) to to_date
        short_from = max(from_date, short_earliest)
        if short_from <= to_date:
            result[short_broker] = (short_from, to_date)

        # Long broker: max(from_date, long_earliest) to (short_from - 1 day)
        long_to = short_from - timedelta(days=1)
        long_from = max(from_date, long_earliest)
        if long_from <= long_to:
            result[long_broker] = (long_from, long_to)

        return result
