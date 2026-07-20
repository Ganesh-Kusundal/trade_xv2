"""Unit tests for token lifecycle event publication."""

from __future__ import annotations

import pytest

from brokers.common.auth.lifecycle import publish_token_lifecycle_event
from domain.events.types import EventType
from infrastructure.event_bus.event_bus import EventBus


@pytest.mark.unit
def test_publish_token_refreshed() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe(
        EventType.TOKEN_REFRESHED.value,
        lambda e: received.append(str(e.payload.get("broker_id", ""))),
    )
    publish_token_lifecycle_event(bus, "TOKEN_REFRESHED", broker_id="dhan")
    assert "dhan" in received


@pytest.mark.unit
def test_publish_token_expired() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe(
        EventType.TOKEN_EXPIRED.value,
        lambda e: received.append(str(e.payload.get("reason", ""))),
    )
    publish_token_lifecycle_event(bus, "TOKEN_EXPIRED", broker_id="upstox", reason="401")
    assert "401" in received
