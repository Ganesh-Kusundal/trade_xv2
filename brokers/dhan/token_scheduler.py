"""Token refresh scheduler — background thread that proactively refreshes tokens.

Runs a daemon thread that calls AuthManager.ensure_valid() at regular intervals,
pushing fresh tokens to DhanHttpClient and WebSocket connections via callbacks.

This service is a :class:`brokers.common.lifecycle.ManagedService`. It is
owned by a :class:`LifecycleManager` so that the process can drain it
deterministically on shutdown, and so that two TokenRefreshScheduler
instances can share a single lock without module-level globals.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from brokers.common.core.auth import AuthManager
from brokers.common.lifecycle import HealthState, ManagedService, build_health

logger = logging.getLogger(__name__)

# Default refresh interval: 20 minutes
_DEFAULT_INTERVAL_SECONDS = 20 * 60

# Default buffer: refresh when 10 minutes remain
_DEFAULT_BUFFER_SECONDS = 600


class TokenRefreshScheduler(ManagedService):
    """Background scheduler that proactively refreshes broker tokens.

    Usage::

        auth = AuthManager(...)
        scheduler = TokenRefreshScheduler(
            auth,
            refresh_lock=my_lock,         # shared with HTTP 401 handler
            on_refresh=my_update_fn,
        )
        lifecycle.register(scheduler)
        lifecycle.start_all()

    Parameters
    ----------
    refresh_lock:
        Optional threading.Lock shared with the HTTP 401 handler so
        that scheduler refreshes and on-demand refreshes do not race.
        If omitted, a private lock is used (single-scheduler mode).
    """

    name: str = "dhan.token_refresh_scheduler"

    def __init__(
        self,
        auth: AuthManager,
        interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
        buffer_seconds: float = _DEFAULT_BUFFER_SECONDS,
        refresh_lock: threading.Lock | None = None,
        on_refresh: Callable[[str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        self._auth = auth
        self._interval = interval_seconds
        self._buffer = buffer_seconds
        # Local lock by default. Pass an explicit lock when sharing
        # with another component (e.g. the HTTP 401 handler). This
        # replaces the previous module-global _token_refresh_lock.
        self._refresh_lock = refresh_lock or threading.Lock()
        self._on_refresh = on_refresh
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_count = 0
        self._last_refresh_at: float | None = None
        self._last_error: str | None = None

    # ── ManagedService contract ──────────────────────────────────────────

    def start(self) -> None:
        """Start the background refresh thread. Idempotent."""
        if self._thread and self._thread.is_alive():
            logger.debug("Token refresh scheduler already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="token-refresh",
        )
        self._thread.start()
        logger.info(
            "Token refresh scheduler started (interval=%ds, buffer=%.0fs)",
            self._interval,
            self._buffer,
        )

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """Stop the background refresh thread. Idempotent."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning(
                    "Token refresh scheduler did not stop within %.1fs; "
                    "leaving the daemon to be reaped at process exit",
                    timeout_seconds,
                )
            self._thread = None
        logger.info(
            "Token refresh scheduler stopped (refreshed %d times)",
            self._refresh_count,
        )

    def health(self):  # type: ignore[override]
        running = self._thread is not None and self._thread.is_alive()
        if not running:
            state = HealthState.STOPPED
            detail = "not running"
        elif self._last_error is not None:
            state = HealthState.DEGRADED
            detail = f"last error: {self._last_error}"
        else:
            state = HealthState.HEALTHY
            detail = f"refreshed {self._refresh_count} times"
        return build_health(
            self.name,
            state,
            detail=detail,
            metrics={
                "refresh_count": self._refresh_count,
                "interval_seconds": self._interval,
                "buffer_seconds": self._buffer,
            },
        )

    # ── Public helpers ───────────────────────────────────────────────────

    def refresh_now(self) -> bool:
        """Trigger an immediate refresh check. Returns True if refreshed."""
        return self._do_refresh()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def refresh_lock(self) -> threading.Lock:
        """Lock shared with the HTTP 401 handler for token refresh coordination."""
        return self._refresh_lock

    # ── Background loop ──────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.error("Token refresh scheduler error: %s", exc)
                if self._on_error:
                    try:
                        self._on_error(exc)
                    except Exception:
                        pass
            self._stop_event.wait(timeout=self._interval)

    def _do_refresh(self) -> bool:
        if not self._refresh_lock.acquire(blocking=False):
            logger.debug(
                "Token refresh already in progress (from HTTP handler); "
                "skipping scheduler refresh"
            )
            return False
        try:
            if self._auth.ensure_valid(buffer_seconds=self._buffer):
                state = self._auth.state
                if state and self._on_refresh:
                    self._on_refresh(state.access_token)
                self._refresh_count += 1
                self._last_refresh_at = time.monotonic()
                self._last_error = None
                logger.debug("Token refresh check passed (count=%d)", self._refresh_count)
                return True
            self._last_error = "no valid token available"
            logger.warning("Token refresh check failed — no valid token available")
            return False
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Token refresh failed: %s", exc)
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception:
                    pass
            return False
        finally:
            self._refresh_lock.release()
