"""Shared token-lifecycle contract — protocol, 401-once policy, broadcast, scheduler.

``DhanTokenManager``/``UpstoxTokenManager`` already share the same
``ensure_token(force_refresh=...)`` / ``current()`` shape; this module makes
that shape a named port so anything (a background scheduler, health probe)
can depend on the abstraction instead of a concrete broker's class, and adds
what neither token manager had: a proactive background refresh loop and a
way to tell already-open connections (e.g. a live WebSocket) that the token
changed, instead of leaving them to notice only on their next reconnect.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TokenLifecyclePort(Protocol):
    """Common shape already implemented by DhanTokenManager/UpstoxTokenManager."""

    def ensure_token(self, *, force_refresh: bool = False) -> str: ...

    def current(self) -> str: ...


def should_attempt_refresh(already_refreshed: bool) -> bool:
    """401-once policy: at most one remint attempt per probe cycle."""
    return not already_refreshed


# ---------------------------------------------------------------------------
# Broadcast — notify live connections when the token changes
# ---------------------------------------------------------------------------
#
# Plain strong references, not weak ones: a v2 token manager lives exactly as
# long as its broker connection, and has at most a couple of receivers
# (e.g. a streaming adapter) registered once for that same lifetime — there's
# no short-lived-subscriber churn to protect against here. Weak refs would add
# a real footgun instead: an inline `register(lambda tok: ...)` with no other
# strong reference gets garbage-collected before the next broadcast, so the
# receiver silently stops firing. Legacy's connections manage many short-lived
# subscriptions and that tradeoff made sense there; it doesn't here.


class TokenBroadcast:
    """Registry of token receivers + broadcast — one instance per broker token manager."""

    def __init__(self) -> None:
        self._receivers: list[Callable[[str], None]] = []

    def register(self, receiver: Callable[[str], None]) -> Callable[[str], None]:
        """Idempotent: registering the same callable twice is a no-op."""
        if receiver not in self._receivers:
            self._receivers.append(receiver)
        return receiver

    def broadcast(self, new_token: str) -> int:
        """Push ``new_token`` to every receiver; isolate per-receiver failures."""
        if not new_token:
            return 0
        delivered = 0
        for receiver in list(self._receivers):
            try:
                receiver(new_token)
                delivered += 1
            except Exception as exc:
                logger.warning(
                    "token_receiver_failed",
                    extra={"receiver": getattr(receiver, "__qualname__", repr(receiver)), "error": str(exc)},
                )
        return delivered

    @property
    def receiver_count(self) -> int:
        return len(self._receivers)


# ---------------------------------------------------------------------------
# Background refresh scheduler
# ---------------------------------------------------------------------------


class TokenRefreshScheduler:
    """Background thread that calls ``ensure_token()`` on an interval.

    Non-forcing: ``ensure_token()`` is probe-before-mint, so a tick that finds
    the current token still valid is a no-op — this never mints proactively,
    only checks. Broadcasts only when the token actually changed.

    Self-contained start/stop rather than the runtime's ``Component`` ABC:
    ``plugins/`` depends only on ``domain/`` + ``shared/`` (composition root
    is the only layer that touches infrastructure), so this owns its own
    minimal lifecycle instead of crossing that boundary for one base class.
    """

    def __init__(
        self,
        broker_id: str,
        token_manager: TokenLifecyclePort,
        *,
        broadcast: TokenBroadcast | None = None,
        interval_seconds: float = 300.0,
    ) -> None:
        self.broker_id = broker_id
        self._token_manager = token_manager
        self._broadcast = broadcast
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._refresh_count = 0
        self._error_count = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_seconds)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self.refresh_now()

    def refresh_now(self) -> bool:
        before = self._token_manager.current()
        try:
            after = self._token_manager.ensure_token()
            self._refresh_count += 1
            if self._broadcast is not None and after and after != before:
                self._broadcast.broadcast(after)
            return True
        except Exception as exc:
            self._error_count += 1
            logger.warning("token_refresh_failed", extra={"broker_id": self.broker_id, "error": str(exc)})
            return False

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def error_count(self) -> int:
        return self._error_count
