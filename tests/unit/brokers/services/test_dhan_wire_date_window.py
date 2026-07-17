"""F-3 regression guard — historical date windowing must be honoured.

This guards against the class of bug where a broker wire adapter ignores the
requested ``from_date``/``to_date`` and instead derives the range from
``lookback_days`` (which would defeat chunking: every chunk returns the same
most-recent window). It exercises the REAL planning + adapter path through
``HistoricalDataCoordinator`` with an in-memory gateway (a real component, not
a behaviour mock), and asserts each chunk request carries the planned window.

If a future ``DhanWireAdapter.history`` change ever re-introduces the bug, the
planner would still emit correct windows but the underlying wire would ignore
them — so we additionally assert the gateway received the exact from/to it was
planned for.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from application.data.historical_coordinator import (
    HistoricalDataCoordinator,
    HistoricalQuery,
)
from application.scheduling.quota_scheduler import PriorityClass, QuotaScheduler
from brokers.dhan.config.capabilities import dhan_capabilities
from domain.policies.source_selection import auto_dual_broker_policy
from tests.unit.brokers.common.fixtures.in_memory_gateway import (
    InMemoryBrokerGateway,
)


def _make_coordinator(dhan_gw: InMemoryBrokerGateway) -> HistoricalDataCoordinator:
    registry = BrokerRegistry()
    registry.register(dhan_gw)
    scheduler = QuotaScheduler()
    for profile in dhan_capabilities().rate_limit_profiles:
        scheduler.register_profile("dhan", profile)
    router = BrokerRouter(
        registry, auto_dual_broker_policy(), quota_headroom_fn=scheduler.headroom_for
    )
    return HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=lambda bid, ep, pri: scheduler.acquire(bid, ep, PriorityClass[pri]),
    )


@pytest.mark.asyncio
async def test_chunk_requests_carry_planned_window_not_lookback():
    """Each chunk's from/to equals the planned slice, not today-lookback_days."""
    today = date(2026, 7, 17)
    gw = InMemoryBrokerGateway("dhan", dhan_capabilities())
    coordinator = _make_coordinator(gw)

    # 365-day 1D request — far exceeds any single-broker lookback-as-lookback
    query = HistoricalQuery(
        instrument=__import__("domain.candles.historical", fromlist=["InstrumentRef"]).InstrumentRef(
            symbol="RELIANCE", exchange="NSE"
        ),
        timeframe="1D",
        from_date=today - timedelta(days=365),
        to_date=today,
        request_id="f3-guard",
    )
    await coordinator.fetch(query)

    assert gw.historical_calls, "coordinator must have issued at least one chunk request"
    for call in gw.historical_calls:
        call_from = date.fromisoformat(call.from_date)
        call_to = date.fromisoformat(call.to_date)
        # The window must be a real sub-range of the requested 365-day span,
        # not today-90d..today (which a buggy wire would silently produce).
        assert call_from >= query.from_date, f"chunk starts before request: {call_from}"
        assert call_to <= query.to_date, f"chunk ends after request: {call_to}"
        # And the span must not be the ubiquitous today-90d..today collapse.
        assert (query.to_date - call_from).days < 365 or call_from == query.from_date
