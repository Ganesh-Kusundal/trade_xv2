"""MessageLog append/read — durable wiring path used by MessageBus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from infrastructure.message_bus import InMemoryMessageLog, MessageBus


@dataclass(frozen=True)
class LoggedEvent:
    name: str
    timestamp: datetime = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


def test_append_messages_and_read_back() -> None:
    log = InMemoryMessageLog()
    bus = MessageBus(message_log=log)

    a = LoggedEvent("a")
    b = LoggedEvent("b")
    bus.publish(a)
    bus.publish(b)

    got = list(log.read())
    assert got == [a, b]


def test_read_filters_by_timestamp_window() -> None:
    log = InMemoryMessageLog()
    early = LoggedEvent("early", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
    mid = LoggedEvent("mid", timestamp=datetime(2024, 6, 1, tzinfo=UTC))
    late = LoggedEvent("late", timestamp=datetime(2024, 12, 1, tzinfo=UTC))
    for msg in (early, mid, late):
        log.append(msg)

    got = list(
        log.read(
            start=datetime(2024, 3, 1, tzinfo=UTC),
            end=datetime(2024, 9, 1, tzinfo=UTC),
        )
    )
    assert got == [mid]


def test_factory_attaches_log_when_persistent_log_enabled() -> None:
    from pathlib import Path

    from config.loader import load_config
    from runtime.factory import RuntimeFactory

    config_dir = Path(__file__).resolve().parents[2] / "config"
    # live profile sets persistent_log: true
    cfg = load_config(config_dir, profile="live")
    assert cfg.components.message_bus.persistent_log is True
    rt = RuntimeFactory.build(cfg)
    assert rt.bus._message_log is not None  # noqa: SLF001
    rt.bus.publish(LoggedEvent("logged"))
    assert list(rt.bus._message_log.read()) == [LoggedEvent("logged")]  # noqa: SLF001
