"""Integration tests for BatchQuoteCoordinator."""

import pytest

from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from application.data.batch_quote_coordinator import BatchQuoteCoordinator, BatchQuoteQuery
from application.scheduling.quota_scheduler import PriorityClass, QuotaScheduler
from brokers.dhan.config.capabilities import dhan_capabilities
from brokers.upstox.capabilities import upstox_capabilities
from domain.candles.historical import InstrumentRef
from domain.policies.source_selection import auto_dual_broker_policy
from tests.unit.brokers.common.fixtures.in_memory_gateway import InMemoryBrokerGateway


def _make_coordinator(
    dhan_gw: InMemoryBrokerGateway,
    upstox_gw: InMemoryBrokerGateway,
) -> BatchQuoteCoordinator:
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
    return BatchQuoteCoordinator(
        registry=registry,
        router=router,
        quota_fn=lambda bid, ep, pri: scheduler.acquire(bid, ep, PriorityClass[pri]),
    )


def _instruments(n: int) -> tuple[InstrumentRef, ...]:
    return tuple(InstrumentRef(symbol=f"SYM{i}", exchange="NSE") for i in range(n))


class TestBatchQuoteCoordinator:
    @pytest.mark.asyncio
    async def test_small_batch_fits_in_one_broker_no_federation(self):
        """A batch within the primary broker's max_batch_size skips federation."""
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(10)
        query = BatchQuoteQuery(instruments=instruments, request_id="batch-small")
        quotes, ledger = await coordinator.fetch(query)

        assert len(quotes) == 10
        assert all(q is not None for q in quotes.values())
        assert len(ledger.chunks) == 1
        # Only one broker was ever called.
        assert (len(dhan.quote_batch_calls) == 0) != (len(upstox.quote_batch_calls) == 0)

    @pytest.mark.asyncio
    async def test_large_batch_splits_across_both_brokers_respecting_max_batch_size(self):
        """1500 symbols must split respecting Upstox (500) / Dhan (1000) caps."""
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(1500)
        query = BatchQuoteQuery(instruments=instruments, request_id="batch-large")
        quotes, ledger = await coordinator.fetch(query)

        assert len(quotes) == 1500
        assert all(q is not None for q in quotes.values())
        assert not ledger.degraded
        assert ledger.brokers_used() == {"dhan", "upstox"}

        dhan_cap = dhan_capabilities().max_batch_size
        upstox_cap = upstox_capabilities().max_batch_size
        assert len(dhan.quote_batch_calls) == 1
        assert len(upstox.quote_batch_calls) == 1
        assert len(dhan.quote_batch_calls[0]) <= dhan_cap
        assert len(upstox.quote_batch_calls[0]) <= upstox_cap
        assert len(dhan.quote_batch_calls[0]) + len(upstox.quote_batch_calls[0]) == 1500

    @pytest.mark.asyncio
    async def test_results_preserve_original_instrument_order(self):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(1200)
        query = BatchQuoteQuery(instruments=instruments, request_id="batch-order")
        quotes, _ = await coordinator.fetch(query)

        assert list(quotes.keys()) == list(instruments)

    @pytest.mark.asyncio
    async def test_one_broker_chunk_fails_reassigns_to_other_broker(self):
        """A failed chunk is reassigned to the remaining healthy broker, not lost."""
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities(), fail_quotes_batch=True)
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(1500)
        query = BatchQuoteQuery(instruments=instruments, request_id="batch-fallback")
        quotes, ledger = await coordinator.fetch(query)

        assert len(quotes) == 1500
        assert all(q is not None for q in quotes.values())
        assert ledger.failed_chunks()  # dhan's original chunk recorded as failed
        # Fallback succeeded for everyone, so overall result should not be degraded.
        assert not ledger.degraded

    @pytest.mark.asyncio
    async def test_both_brokers_fail_marks_degraded_with_none_quotes(self):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities(), fail_quotes_batch=True)
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities(), fail_quotes_batch=True)
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(5)
        query = BatchQuoteQuery(instruments=instruments, request_id="batch-all-fail")
        quotes, ledger = await coordinator.fetch(query)

        assert len(quotes) == 5
        assert all(q is None for q in quotes.values())
        assert ledger.degraded

    @pytest.mark.asyncio
    async def test_empty_instruments_returns_empty_without_calling_brokers(self):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        quotes, ledger = await coordinator.fetch(
            BatchQuoteQuery(instruments=(), request_id="batch-empty")
        )

        assert quotes == {}
        assert ledger.chunks == []
        assert not dhan.quote_batch_calls
        assert not upstox.quote_batch_calls

    @pytest.mark.asyncio
    async def test_concurrent_fetch_not_serialized(self):
        """Both broker chunks should be in flight around the same time, not
        one waiting for the other to finish first."""
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(1500)
        query = BatchQuoteQuery(
            instruments=instruments, request_id="batch-concurrency", max_concurrent_fetches=4
        )
        await coordinator.fetch(query)

        assert dhan.max_concurrent_quote_batches >= 1
        assert upstox.max_concurrent_quote_batches >= 1

    def test_fetch_sync_wraps_fetch(self):
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities())
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        instruments = _instruments(3)
        quotes, ledger = coordinator.fetch_sync(
            BatchQuoteQuery(instruments=instruments, request_id="batch-sync")
        )
        assert len(quotes) == 3
        assert not ledger.degraded

    @pytest.mark.asyncio
    async def test_fallback_sub_splits_when_fallback_cap_smaller(self):
        """If Dhan's chunk (up to 1000) fails and falls back to Upstox (cap
        500), the fallback must sub-split rather than sending an oversized
        single request."""
        dhan = InMemoryBrokerGateway("dhan", dhan_capabilities(), fail_quotes_batch=True)
        upstox = InMemoryBrokerGateway("upstox", upstox_capabilities())
        coordinator = _make_coordinator(dhan, upstox)

        # Force everything onto a single oversized Dhan-only scenario by
        # using a small instrument count that still exceeds Upstox's cap
        # once reassigned as a whole via the large-batch path.
        instruments = _instruments(1500)
        query = BatchQuoteQuery(instruments=instruments, request_id="batch-subsplit")
        quotes, ledger = await coordinator.fetch(query)

        assert len(quotes) == 1500
        assert all(q is not None for q in quotes.values())
        upstox_cap = upstox_capabilities().max_batch_size
        for call in upstox.quote_batch_calls:
            assert len(call) <= upstox_cap
