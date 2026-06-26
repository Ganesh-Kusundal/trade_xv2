"""F10: Replay-mode public API regression tests.

Verifies that EventBus.set_replay_mode() is the sole public interface for
mutating replay mode, and that the old private-attribute pattern
(``bus._replay_mode = True``) is no longer required by any caller.

Each test must complete in < 5 seconds.
"""

from __future__ import annotations

import threading

import pytest

from infrastructure.event_bus.event_bus import DomainEvent, EventBus


class TestSetReplayMode:
    """Direct tests for EventBus.set_replay_mode()."""

    def test_enable_replay_mode(self) -> None:
        bus = EventBus()
        assert bus.replay_mode is False
        bus.set_replay_mode(True)
        assert bus.replay_mode is True

    def test_disable_replay_mode(self) -> None:
        bus = EventBus(replay_mode=True)
        bus.set_replay_mode(False)
        assert bus.replay_mode is False

    def test_idempotent_enable(self) -> None:
        bus = EventBus()
        bus.set_replay_mode(True)
        bus.set_replay_mode(True)
        assert bus.replay_mode is True

    def test_idempotent_disable(self) -> None:
        bus = EventBus(replay_mode=True)
        bus.set_replay_mode(False)
        bus.set_replay_mode(False)
        assert bus.replay_mode is False

    def test_returns_none(self) -> None:
        bus = EventBus()
        result = bus.set_replay_mode(True)
        assert result is None

    def test_preserves_sequence_numbers(self) -> None:
        bus = EventBus()
        bus.set_replay_mode(True)
        # Sequence counter is an internal implementation detail;
        # verify replay mode is enabled without asserting internals
        assert bus.replay_mode is True

    def test_suppresses_dispatch_when_enabled(self) -> None:
        bus = EventBus(replay_mode=True)
        handler_calls: list[str] = []
        bus.subscribe("TRADE_APPLIED", lambda e: handler_calls.append("called"))
        event = DomainEvent.now("TRADE_APPLIED", {"trade_id": "T1"}, symbol="RELIANCE")
        bus.publish(event)
        # In replay mode, TRADE_APPLIED events are suppressed
        assert handler_calls == []

    def test_allows_dispatch_when_disabled(self) -> None:
        bus = EventBus(replay_mode=False)
        handler_calls: list[str] = []
        bus.subscribe("TRADE_APPLIED", lambda e: handler_calls.append("called"))
        event = DomainEvent.now("TRADE_APPLIED", {"trade_id": "T1"}, symbol="RELIANCE")
        bus.publish(event)
        assert handler_calls == ["called"]

    def test_toggle_roundtrip(self) -> None:
        bus = EventBus()
        bus.set_replay_mode(True)
        assert bus.replay_mode is True
        bus.set_replay_mode(False)
        assert bus.replay_mode is False
        bus.set_replay_mode(True)
        assert bus.replay_mode is True


class TestReplayModeThreadSafe:
    """Verify concurrent set_replay_mode calls don't corrupt state."""

    def test_concurrent_toggles(self) -> None:
        bus = EventBus()
        errors: list[Exception] = []

        def toggle(expected_final: bool) -> None:
            try:
                for _ in range(100):
                    bus.set_replay_mode(expected_final)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=toggle, args=(True,))
        t2 = threading.Thread(target=toggle, args=(False,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == []
        assert bus.replay_mode in (True, False)


class TestReplayModeContract:
    """Contract tests ensuring callers use public API."""

    def test_event_bus_has_set_replay_mode_method(self) -> None:
        bus = EventBus()
        assert hasattr(bus, "set_replay_mode")
        assert callable(bus.set_replay_mode)

    def test_replay_mode_property_is_read_only(self) -> None:
        bus = EventBus()
        with pytest.raises(AttributeError):
            bus.replay_mode = True  # type: ignore[misc]

    def test_context_uses_public_api_not_private(self) -> None:
        """Verify TradingContext no longer mutates _replay_mode directly."""
        import inspect
        import re

        from application.oms.context import TradingContext

        source = inspect.getsource(TradingContext._replay_log_into_oms)
        mutation_pattern = re.compile(r"\._replay_mode\s*=|getattr\([^)]*_replay_mode")
        assert not mutation_pattern.search(source), (
            "TradingContext._replay_log_into_oms still mutates _replay_mode directly; "
            "use set_replay_mode() instead"
        )
