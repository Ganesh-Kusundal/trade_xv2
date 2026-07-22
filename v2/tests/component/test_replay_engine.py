"""ReplayEngine republishes MessageLog through bus — handlers see same count."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from application.analytics.engines import ReplayEngine
from infrastructure.message_bus.bus import MessageBus
from infrastructure.message_bus.message_log import InMemoryMessageLog


@dataclass(frozen=True)
class _Tick:
    n: int
    timestamp: datetime = datetime(2024, 1, 1, tzinfo=UTC)


def test_replay_log_handlers_see_same_count() -> None:
    log = InMemoryMessageLog()
    record_bus = MessageBus(message_log=log)
    for i in range(5):
        record_bus.publish(_Tick(n=i, timestamp=datetime(2024, 1, 1, i, tzinfo=UTC)))

    replay_bus = MessageBus()
    seen: list[_Tick] = []
    replay_bus.subscribe(_Tick, seen.append)

    count = ReplayEngine(bus=replay_bus, message_log=log).run()

    assert count == 5
    assert len(seen) == 5
    assert [t.n for t in seen] == list(range(5))
