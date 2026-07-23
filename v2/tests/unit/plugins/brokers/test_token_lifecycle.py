"""TokenBroadcast + TokenRefreshScheduler — shared token-lifecycle depth."""

from __future__ import annotations

import time

from plugins.brokers.common.token_lifecycle import (
    TokenBroadcast,
    TokenLifecyclePort,
    TokenRefreshScheduler,
    should_attempt_refresh,
)


def test_should_attempt_refresh_is_401_once() -> None:
    assert should_attempt_refresh(already_refreshed=False) is True
    assert should_attempt_refresh(already_refreshed=True) is False


class _FakeTokenManager:
    """Satisfies TokenLifecyclePort: current() + ensure_token()."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = list(tokens)
        self._current = tokens[0] if tokens else ""

    def current(self) -> str:
        return self._current

    def ensure_token(self, *, force_refresh: bool = False) -> str:
        if len(self._tokens) > 1:
            self._tokens.pop(0)
        self._current = self._tokens[0]
        return self._current


def test_fake_token_manager_satisfies_protocol() -> None:
    assert isinstance(_FakeTokenManager(["tok-a"]), TokenLifecyclePort)


class TestTokenBroadcast:
    def test_broadcast_delivers_to_all_registered_receivers(self) -> None:
        broadcast = TokenBroadcast()
        received: list[str] = []
        broadcast.register(lambda tok: received.append(tok))
        broadcast.register(lambda tok: received.append(tok.upper()))

        delivered = broadcast.broadcast("new-token")

        assert delivered == 2
        assert received == ["new-token", "NEW-TOKEN"]

    def test_register_same_callable_twice_is_idempotent(self) -> None:
        broadcast = TokenBroadcast()
        received: list[str] = []

        def receiver(tok: str) -> None:
            received.append(tok)

        broadcast.register(receiver)
        broadcast.register(receiver)
        broadcast.broadcast("tok")

        assert received == ["tok"]
        assert broadcast.receiver_count == 1

    def test_broadcast_empty_token_is_noop(self) -> None:
        broadcast = TokenBroadcast()
        received: list[str] = []
        broadcast.register(lambda tok: received.append(tok))
        assert broadcast.broadcast("") == 0
        assert received == []

    def test_one_receiver_failing_does_not_block_others(self) -> None:
        broadcast = TokenBroadcast()
        received: list[str] = []

        def bad_receiver(tok: str) -> None:
            raise RuntimeError("boom")

        broadcast.register(bad_receiver)
        broadcast.register(lambda tok: received.append(tok))

        delivered = broadcast.broadcast("tok")

        assert delivered == 1
        assert received == ["tok"]

    def test_bound_method_receiver_stays_registered_for_broadcast_lifetime(self) -> None:
        """Strong refs by design: a receiver stays registered until it unregisters
        itself, not until something else happens to drop its last reference."""
        broadcast = TokenBroadcast()

        class _Sink:
            def __init__(self) -> None:
                self.received: list[str] = []

            def receive(self, tok: str) -> None:
                self.received.append(tok)

        sink = _Sink()
        broadcast.register(sink.receive)
        assert broadcast.receiver_count == 1

        broadcast.broadcast("tok")
        assert sink.received == ["tok"]


class TestTokenRefreshScheduler:
    def test_refresh_now_broadcasts_only_when_token_changed(self) -> None:
        manager = _FakeTokenManager(["tok-a", "tok-b"])
        broadcast = TokenBroadcast()
        received: list[str] = []
        broadcast.register(lambda tok: received.append(tok))
        scheduler = TokenRefreshScheduler("dhan", manager, broadcast=broadcast)

        scheduler.refresh_now()
        assert received == ["tok-b"]
        assert scheduler.refresh_count == 1
        assert scheduler.error_count == 0

    def test_refresh_now_no_broadcast_when_token_unchanged(self) -> None:
        manager = _FakeTokenManager(["tok-a"])
        broadcast = TokenBroadcast()
        received: list[str] = []
        broadcast.register(lambda tok: received.append(tok))
        scheduler = TokenRefreshScheduler("dhan", manager, broadcast=broadcast)

        scheduler.refresh_now()
        assert received == []

    def test_refresh_now_records_error_on_exception(self) -> None:
        class _FailingManager:
            def current(self) -> str:
                return "tok"

            def ensure_token(self, *, force_refresh: bool = False) -> str:
                raise RuntimeError("mint failed")

        scheduler = TokenRefreshScheduler("dhan", _FailingManager())
        assert scheduler.refresh_now() is False
        assert scheduler.error_count == 1
        assert scheduler.refresh_count == 0

    def test_start_stop_runs_background_thread(self) -> None:
        manager = _FakeTokenManager(["tok-a", "tok-b", "tok-b"])
        scheduler = TokenRefreshScheduler("dhan", manager, interval_seconds=0.02)
        scheduler.start()
        assert scheduler.is_running is True
        time.sleep(0.08)
        scheduler.stop()
        assert scheduler.is_running is False
        assert scheduler.refresh_count >= 1
