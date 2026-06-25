"""Integration tests for StreamOrchestrator health and subscription lifecycle."""

import pytest

from brokers.common.capabilities import dhan_capabilities, upstox_capabilities
from brokers.common.policy import auto_dual_broker_policy
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from brokers.common.stream_orchestrator import (
    MarketTick,
    StreamOrchestrator,
    SubscriptionRequest,
)
from brokers.common.tests.fixtures.in_memory_gateway import InMemoryBrokerGateway
from domain.stream_health import FreshnessState, SubscriptionState, TransportState


class _RecordingConsumer:
    def __init__(self, consumer_id: str = "consumer-1") -> None:
        self._id = consumer_id
        self.ticks: list[MarketTick] = []

    def consumer_id(self) -> str:
        return self._id

    async def on_market_tick(self, tick: MarketTick) -> None:
        self.ticks.append(tick)

    async def on_order_update(self, update) -> None:
        pass

    async def on_stream_health_change(self, session_id: str, health) -> None:
        pass


@pytest.fixture
async def orchestrator():
    registry = BrokerRegistry()
    registry.register(InMemoryBrokerGateway("dhan", dhan_capabilities()))
    registry.register(InMemoryBrokerGateway("upstox", upstox_capabilities()))
    router = BrokerRouter(registry, auto_dual_broker_policy())
    orch = StreamOrchestrator(registry=registry, router=router)
    await orch.start()
    yield orch
    await orch.stop()


class TestStreamOrchestrator:
    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription_id(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        assert sub_id
        await orchestrator.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_session_created_and_healthy_after_subscribe(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        sessions = orchestrator.all_sessions()
        assert len(sessions) >= 1
        session = sessions[0]
        assert session.broker_id in {"dhan", "upstox"}
        assert session.health.transport == TransportState.CONNECTED
        assert session.health.subscription == SubscriptionState.ACKNOWLEDGED
        await orchestrator.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_deliver_tick_updates_freshness(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        session = orchestrator.all_sessions()[0]
        tick = orchestrator._normalize_tick(
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": 2500.0, "volume": 100},
            session.session_id,
            session.broker_id,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        assert tick is not None
        await orchestrator._deliver_tick(session.session_id, tick)
        assert consumer.ticks
        health = orchestrator.session_health(session.session_id)
        assert health is not None
        assert health.freshness == FreshnessState.FRESH
        await orchestrator.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_session_when_last_consumer(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="order",
                consumer=consumer,
                instruments=frozenset(),
                modes=frozenset(),
            )
        )
        assert orchestrator.all_sessions()
        await orchestrator.unsubscribe(sub_id)
        assert orchestrator.all_sessions() == []

    @pytest.mark.asyncio
    async def test_build_stream_summary(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        session = orchestrator.all_sessions()[0]
        summary = orchestrator.build_stream_summary(session.broker_id)
        assert summary.active_sessions >= 1
        # Freshness starts UNKNOWN until first tick — not yet healthy
        assert summary.healthy_sessions == 0
        await orchestrator.unsubscribe(sub_id)

    def test_stream_health_stale_when_freshness_not_within_sla(self):
        from domain.stream_health import StreamHealth

        health = StreamHealth(
            transport=TransportState.CONNECTED,
            subscription=SubscriptionState.ACKNOWLEDGED,
            freshness=FreshnessState.STALE,
        )
        assert not health.healthy()
        assert any("freshness" in r for r in health.failure_reasons())
