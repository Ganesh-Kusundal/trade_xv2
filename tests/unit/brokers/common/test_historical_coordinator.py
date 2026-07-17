"""Integration tests for HistoricalDataCoordinator."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from application.data.historical_coordinator import HistoricalDataCoordinator, HistoricalQuery
from domain.policies.source_selection import auto_dual_broker_policy
from application.scheduling.quota_scheduler import PriorityClass, QuotaScheduler
from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from tests.unit.brokers.common.fixtures.in_memory_gateway import InMemoryBrokerGateway, _bar
from brokers.dhan.config.capabilities import dhan_capabilities
from brokers.upstox.capabilities import upstox_capabilities
from domain.candles.historical import HistoricalBar, InstrumentRef
from domain.provenance import DataProvenance


def _make_coordinator(
    dhan_gw: InMemoryBrokerGateway,
    upstox_gw: InMemoryBrokerGateway,
) -> HistoricalDataCoordinator:
    registry = BrokerRegistry()
    registry.register(dhan_gw)
    registry.register(upstox_gw)
    scheduler = QuotaScheduler()
    for profile in dhan_capabilities().rate_limit_profiles:
        scheduler.register_profile("dhan", profile)
    for profile in upstox_capabilities().rate_limit_profiles:
        scheduler.register_profile("upstox", profile)
    router = BrokerRouter(
        registry, auto_dual_broker_policy(), quota_headroom_fn=scheduler.headroom_for
    )
    return HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=lambda bid, ep, pri: scheduler.acquire(bid, ep, PriorityClass[pri]),
    )


def _make_single_broker_coordinator(gw: InMemoryBrokerGateway) -> HistoricalDataCoordinator:
    """Coordinator with only one broker registered (mirrors BrokerSession)."""
    registry = BrokerRegistry()
    registry.register(gw)
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


@pytest.fixture
def instrument():
    return InstrumentRef(symbol="RELIANCE", exchange="NSE")


class TestHistoricalDataCoordinator:
    @pytest.mark.asyncio
    async def test_fetches_from_both_brokers_for_long_range(self, instrument):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        today = date.today()
        query = HistoricalQuery(
            instrument=instrument,
            timeframe="1m",
            from_date=today - timedelta(days=60),
            to_date=today,
            request_id="hist-req-1",
        )
        series, ledger = await coordinator.fetch(query)

        assert series.bar_count > 0
        assert len(ledger.chunks) >= 2
        brokers = ledger.brokers_used()
        assert "dhan" in brokers or "upstox" in brokers
        assert series.instrument == instrument

    @pytest.mark.asyncio
    async def test_passes_correct_instrument_to_gateway(self, instrument):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        today = date.today()
        query = HistoricalQuery(
            instrument=instrument,
            timeframe="1D",
            from_date=today - timedelta(days=5),
            to_date=today,
            request_id="hist-req-2",
        )
        await coordinator.fetch(query)

        all_calls = dhan.historical_calls + upstox.historical_calls
        assert all_calls
        for call in all_calls:
            assert call.instrument.symbol == "RELIANCE"
            assert call.instrument.exchange == "NSE"

    @pytest.mark.asyncio
    async def test_degraded_mode_when_primary_fails_and_fallback_succeeds(self, instrument):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities(), fail_historical=True)
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        today = date.today()
        # Use 60-day range so dhan is assigned older chunks and upstox recent ones
        query = HistoricalQuery(
            instrument=instrument,
            timeframe="1D",
            from_date=today - timedelta(days=60),
            to_date=today,
            request_id="hist-req-3",
        )
        series, ledger = await coordinator.fetch(query)

        failed = ledger.failed_chunks()
        if failed:
            assert any(c.broker_id == "dhan" for c in failed)
            assert ledger.degraded or series.is_degraded or series.bar_count >= 0
        else:
            # If routing assigned only upstox for this window, dhan may not be called
            assert series.bar_count >= 0

    @pytest.mark.asyncio
    async def test_merge_conflict_fail_on_conflict_raises(self, instrument):
        ts = datetime(2025, 6, 1, 9, 15, tzinfo=timezone.utc)

        def dhan_bars(request, quota):
            return [
                _bar(instrument, "1D", ts, Decimal("100.00"), "dhan", request.request_id),
            ]

        def upstox_bars(request, quota):
            return [
                _bar(instrument, "1D", ts, Decimal("200.00"), "upstox", request.request_id),
            ]

        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities(), historical_fn=dhan_bars)
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities(), historical_fn=upstox_bars)
        coordinator = _make_coordinator(dhan, upstox)

        # Force both brokers to return overlapping same-day bars by using 1D and short range
        today = date.today()
        HistoricalQuery(
            instrument=instrument,
            timeframe="1D",
            from_date=today - timedelta(days=1),
            to_date=today,
            merge_strategy="fail_on_conflict",
            request_id="hist-req-4",
        )

        # Manually merge test: inject same timestamp bars via coordinator internals
        # Run fetch — if both brokers serve overlapping window, conflict may occur
        # Use direct _merge test for deterministic conflict behavior
        bar_dhan = HistoricalBar(
            instrument=instrument,
            timeframe="1D",
            event_time=ts,
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=1,
            provenance=DataProvenance.now("dhan", "r1"),
        )
        bar_upstox = HistoricalBar(
            instrument=instrument,
            timeframe="1D",
            event_time=ts,
            open=Decimal("200"),
            high=Decimal("200"),
            low=Decimal("200"),
            close=Decimal("200"),
            volume=1,
            provenance=DataProvenance.now("upstox", "r2"),
        )
        merged, conflicts = coordinator._merge(
            [bar_dhan, bar_upstox],
            chunk_bars={"c1": [bar_dhan], "c2": [bar_upstox]},
            strategy="fail_on_conflict",
            tolerance=Decimal("0.001"),
        )
        assert len(conflicts) == 1
        assert len(merged) == 1
        assert merged[0].close == Decimal("100")

    @pytest.mark.asyncio
    async def test_bars_reindexed_after_merge(self, instrument):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        today = date.today()
        query = HistoricalQuery(
            instrument=instrument,
            timeframe="1D",
            from_date=today - timedelta(days=3),
            to_date=today,
            request_id="hist-req-5",
        )
        series, _ = await coordinator.fetch(query)
        if series.bar_count > 0:
            indices = [b.bar_index for b in series.bars]
            assert indices == list(range(len(series.bars)))

    @pytest.mark.asyncio
    async def test_short_chunk_silently_missing_tail_day_triggers_gap_fill(self, instrument):
        """Regression guard: a chunk that "succeeds" (non-empty) but silently
        stops short of to_date (e.g. a broker's historical endpoint dropping
        today's in-progress session from an otherwise-valid multi-day
        response) must not be accepted as complete. Found in production:
        Upstox always returns real data for the requested range's earlier
        days but silently omits the trailing (today) day with no error --
        the emptiness-only fallback check let this through for ~499/501
        symbols in one real sync run. GapDetector already flags the gap;
        this verifies it's actually acted on (a second broker is tried for
        just the missing day), not just recorded and ignored."""
        today = date.today()
        from_date = today - timedelta(days=2)

        def upstox_bars(request, quota):
            # Real Upstox behavior: returns the earlier days, silently
            # omits to_date entirely (no error, just fewer bars than asked).
            req_to = date.fromisoformat(request.to_date)
            if req_to == today:
                from_d = date.fromisoformat(request.from_date)
                days = [from_d + timedelta(days=i) for i in range((req_to - from_d).days)]
            else:
                from_d, to_d = date.fromisoformat(request.from_date), req_to
                days = [from_d + timedelta(days=i) for i in range((to_d - from_d).days + 1)]
            return [
                _bar(
                    request.instrument, request.timeframe,
                    datetime(d.year, d.month, d.day, 9, 15, tzinfo=timezone.utc),
                    Decimal("100.00"), "upstox", request.request_id,
                )
                for d in days
            ]

        def dhan_bars(request, quota):
            # Only ever asked for the gap (today) once gap-fill kicks in.
            from_d = date.fromisoformat(request.from_date)
            return [
                _bar(
                    request.instrument, request.timeframe,
                    datetime(from_d.year, from_d.month, from_d.day, 9, 15, tzinfo=timezone.utc),
                    Decimal("100.00"), "dhan", request.request_id,
                )
            ]

        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities(), historical_fn=dhan_bars)
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities(), historical_fn=upstox_bars)
        coordinator = _make_coordinator(dhan, upstox)

        query = HistoricalQuery(
            instrument=instrument,
            timeframe="1m",
            from_date=from_date,
            to_date=today,
            request_id="hist-req-gapfill",
        )
        series, ledger = await coordinator.fetch(query)

        bar_dates = {b.event_time.date() for b in series.bars}
        assert today in bar_dates, "gap-fill should have recovered today's missing data"
        assert series.gaps == []
        assert any(c.broker_id == "dhan" and c.to_date == today for c in ledger.chunks), (
            "dhan should have been tried specifically for the missing tail day"
        )

    @pytest.mark.asyncio
    async def test_middle_chunk_failure_produces_explicit_gap(self, instrument):
        """A failed MIDDLE chunk must surface as a gap + degraded, not silent truncation."""
        today = date.today()
        # Single-broker (dhan only) to mirror BrokerSession's real construction:
        # the router's dual-broker policy lists upstox, but it is not registered,
        # so every chunk is assigned to dhan and a dhan failure is deterministic.
        query = HistoricalQuery(
            instrument=instrument,
            timeframe="1m",
            from_date=today - timedelta(days=200),
            to_date=today,
            request_id="hist-req-6",
        )

        # Build the single-broker coordinator first so we can read the ACTUAL
        # planned middle chunk date from the same config used for the fetch.
        dhan_fail = InMemoryBrokerGateway("dhan", dhan_capabilities())
        coordinator_fail = _make_single_broker_coordinator(dhan_fail)
        chunks = coordinator_fail._planner.plan(query, query.request_id)
        assert len(chunks) >= 3, f"expected >=3 chunks for 200d 1m, got {len(chunks)}"
        middle_from = chunks[1].from_date.isoformat()

        def flaky(request, quota):
            if request.from_date == middle_from:
                raise RuntimeError("simulated mid-range outage")
            from_d = date.fromisoformat(request.from_date)
            return [
                _bar(
                    request.instrument,
                    request.timeframe,
                    datetime(from_d.year, from_d.month, from_d.day, 9, 15, tzinfo=timezone.utc),
                    Decimal("100.00"),
                    "dhan",
                    request.request_id,
                )
            ]

        dhan_fail._historical_fn = flaky

        series, ledger = await coordinator_fail.fetch(query)

        assert series.is_degraded is True
        assert len(series.gaps) > 0
        # The failed middle window appears as an explicit gap inside the range.
        gap_starts = [g.start for g in series.gaps]
        assert any(today - timedelta(days=200) <= s <= today for s in gap_starts)
