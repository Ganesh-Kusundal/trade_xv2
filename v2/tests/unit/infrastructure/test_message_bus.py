"""TDD tests for MessageBus, MessageRouter, and MessageLog infrastructure."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterator

import pytest

from domain.messages import Message
from domain.value_objects import InstrumentId, StrategyId, AccountId, Timestamp
from infrastructure.message_bus.bus import MessageBus, MessageBusMetrics
from infrastructure.message_bus.router import MessageRouter
from infrastructure.message_bus.log import MessageLog, InMemoryMessageLog


# Test message types with the fields needed for routing
@dataclass(frozen=True, slots=True, kw_only=True)
class SampleMessage(Message):
    value: int = 0
    instrument_id: InstrumentId | None = None
    strategy_id: StrategyId | None = None
    account_id: AccountId | None = None
    session_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AnotherMessage(Message):
    data: str = ""


class TestMessageBus:
    """Test MessageBus core functionality."""

    def test_publish_delivers_to_subscribers(self) -> None:
        """Test that publish delivers messages to registered handlers."""
        bus = MessageBus()
        received: list[SampleMessage] = []
        
        bus.subscribe(SampleMessage, received.append)
        msg = SampleMessage(timestamp=1000, value=42)
        bus.publish(msg)
        
        assert received == [msg]
        assert bus.metrics.messages_published == 1
        assert bus.metrics.messages_delivered == 1
        assert bus.metrics.messages_failed == 0

    def test_unsubscribe_stops_delivery(self) -> None:
        """Test that unsubscribe stops message delivery."""
        bus = MessageBus()
        received: list[SampleMessage] = []
        
        sub = bus.subscribe(SampleMessage, received.append)
        bus.unsubscribe(sub)
        
        bus.publish(SampleMessage(timestamp=1000, value=1))
        assert received == []
        assert bus.metrics.messages_published == 1
        assert bus.metrics.messages_delivered == 0

    def test_multiple_subscribers_receive_same_message(self) -> None:
        """Test that multiple subscribers for the same type all receive messages."""
        bus = MessageBus()
        received1: list[SampleMessage] = []
        received2: list[SampleMessage] = []
        
        bus.subscribe(SampleMessage, received1.append)
        bus.subscribe(SampleMessage, received2.append)
        
        msg = SampleMessage(timestamp=1000, value=99)
        bus.publish(msg)
        
        assert received1 == [msg]
        assert received2 == [msg]
        assert bus.metrics.messages_delivered == 2

    def test_message_type_filtering(self) -> None:
        """Test that handlers only receive messages of their subscribed type."""
        bus = MessageBus()
        test_received: list[SampleMessage] = []
        another_received: list[AnotherMessage] = []
        
        bus.subscribe(SampleMessage, test_received.append)
        bus.subscribe(AnotherMessage, another_received.append)
        
        test_msg = SampleMessage(timestamp=1000, value=1)
        another_msg = AnotherMessage(timestamp=2000, data="hello")
        
        bus.publish(test_msg)
        bus.publish(another_msg)
        
        assert test_received == [test_msg]
        assert another_received == [another_msg]

    def test_handler_exception_goes_to_dlq(self) -> None:
        """Test that handler exceptions create dead letters."""
        bus = MessageBus()
        
        def failing_handler(msg: SampleMessage) -> None:
            raise ValueError("test error")
        
        bus.subscribe(SampleMessage, failing_handler)
        bus.publish(SampleMessage(timestamp=1000, value=1))
        
        assert len(bus.dead_letters) == 1
        dl = bus.dead_letters[0]
        assert dl.original_message == SampleMessage(timestamp=1000, value=1)
        assert "test error" in dl.error
        assert bus.metrics.messages_failed == 1
        assert bus.metrics.dlq_count == 1

    def test_metrics_increment_correctly(self) -> None:
        """Test that all metrics increment correctly."""
        bus = MessageBus()
        
        def handler(msg: SampleMessage) -> None:
            if msg.value < 0:
                raise ValueError("negative")
        
        bus.subscribe(SampleMessage, handler)
        
        # Publish successful messages
        bus.publish(SampleMessage(timestamp=1000, value=1))
        bus.publish(SampleMessage(timestamp=2000, value=2))
        
        # Publish failing message
        bus.publish(SampleMessage(timestamp=3000, value=-1))
        
        assert bus.metrics.messages_published == 3
        assert bus.metrics.messages_delivered == 2
        assert bus.metrics.messages_failed == 1
        assert bus.metrics.dlq_count == 1

    def test_avg_latency_ns_calculation(self) -> None:
        """Test that average latency is calculated correctly."""
        bus = MessageBus()
        received: list[SampleMessage] = []
        
        bus.subscribe(SampleMessage, received.append)
        bus.publish(SampleMessage(timestamp=1000, value=1))
        
        # Latency should be non-negative
        assert bus.metrics.avg_latency_ns >= 0


class TestMessageRouter:
    """Test MessageRouter functionality."""

    def test_route_with_instrument_filter(self) -> None:
        """Test routing with instrument filter."""
        router = MessageRouter()
        received: list[SampleMessage] = []
        
        builder = router.route(SampleMessage, instrument=InstrumentId("AAPL"))
        builder.to(received.append)
        
        # Publish matching message
        msg = SampleMessage(timestamp=1000, value=1, instrument_id=InstrumentId("AAPL"))
        router.publish(msg)
        
        assert received == [msg]

    def test_route_with_strategy_filter(self) -> None:
        """Test routing with strategy filter."""
        router = MessageRouter()
        received: list[SampleMessage] = []
        
        builder = router.route(SampleMessage, strategy=StrategyId("momentum"))
        builder.to(received.append)
        
        msg = SampleMessage(timestamp=1000, value=1, strategy_id=StrategyId("momentum"))
        router.publish(msg)
        
        assert received == [msg]

    def test_wire_shorthand(self) -> None:
        """Test wire as shorthand for route().to()."""
        router = MessageRouter()
        received: list[SampleMessage] = []
        
        router.wire(SampleMessage, received.append, instrument=InstrumentId("AAPL"))
        
        msg = SampleMessage(timestamp=1000, value=1, instrument_id=InstrumentId("AAPL"))
        router.publish(msg)
        
        assert received == [msg]

    def test_route_filters_mismatched_instruments(self) -> None:
        """Test that route filters out messages with wrong instrument."""
        router = MessageRouter()
        received: list[SampleMessage] = []
        
        builder = router.route(SampleMessage, instrument=InstrumentId("AAPL"))
        builder.to(received.append)
        
        # Publish message with different instrument
        msg = SampleMessage(timestamp=1000, value=1, instrument_id=InstrumentId("GOOGL"))
        router.publish(msg)
        
        assert received == []


class TestMessageLog:
    """Test MessageLog protocol and InMemoryMessageLog."""

    def test_append_and_read(self) -> None:
        """Test appending and reading messages."""
        log = InMemoryMessageLog()
        
        msg1 = SampleMessage(timestamp=1000, value=1)
        msg2 = SampleMessage(timestamp=2000, value=2)
        
        log.append(msg1)
        log.append(msg2)
        
        messages = list(log.read(start=0, end=3000))
        assert messages == [msg1, msg2]

    def test_read_session(self) -> None:
        """Test reading messages by session ID."""
        log = InMemoryMessageLog()
        
        msg1 = SampleMessage(timestamp=1000, value=1, session_id="session-1")
        msg2 = SampleMessage(timestamp=2000, value=2, session_id="session-2")
        
        log.append(msg1)
        log.append(msg2)
        
        session_msgs = list(log.read_session("session-1"))
        assert session_msgs == [msg1]

    def test_clear(self) -> None:
        """Test clearing the log."""
        log = InMemoryMessageLog()
        
        log.append(SampleMessage(timestamp=1000, value=1))
        log.append(SampleMessage(timestamp=2000, value=2))
        
        log.clear()
        messages = list(log.read(start=0, end=3000))
        assert messages == []


class TestMessageBusMetrics:
    """Test MessageBusMetrics dataclass."""

    def test_initial_metrics(self) -> None:
        """Test that metrics start at zero."""
        metrics = MessageBusMetrics()
        
        assert metrics.messages_published == 0
        assert metrics.messages_delivered == 0
        assert metrics.messages_failed == 0
        assert metrics.dlq_count == 0
        assert metrics.avg_latency_ns == 0
