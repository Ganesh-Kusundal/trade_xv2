"""Component tests for broker lifecycle event publication."""

from __future__ import annotations

import pytest

from brokers.providers.paper.paper_gateway import PaperGateway
from brokers.session.broker_session import BrokerSession
from domain.events.types import EventType
from domain.ports.broker_session_state import BrokerSessionState
from domain.session import Session
from infrastructure.event_bus.event_bus import EventBus


@pytest.mark.component
def test_broker_connected_event_published() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe(
        EventType.BROKER_CONNECTED.value,
        lambda e: received.append(str(e.payload.get("broker_id", ""))),
    )
    session = BrokerSession.__new__(BrokerSession)
    session._broker_id = "paper"
    session._session_state = BrokerSessionState.HEALTHY
    session._session = Session(PaperGateway(), event_bus=bus)
    session._publish_lifecycle_event("BROKER_CONNECTED")
    assert "paper" in received


@pytest.mark.component
def test_broker_disconnected_event_published() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe(
        EventType.BROKER_DISCONNECTED.value,
        lambda e: received.append(str(e.payload.get("broker_id", ""))),
    )
    session = BrokerSession.__new__(BrokerSession)
    session._broker_id = "paper"
    session._session_state = BrokerSessionState.HEALTHY
    session._session = Session(PaperGateway(), event_bus=bus)
    session._publish_lifecycle_event("BROKER_DISCONNECTED")
    assert "paper" in received
