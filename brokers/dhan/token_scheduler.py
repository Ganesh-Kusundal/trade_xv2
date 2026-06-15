"""Token refresh scheduler — background thread that proactively refreshes tokens.

Runs a daemon thread that calls AuthManager.ensure_valid() at regular intervals,
pushing fresh tokens to DhanHttpClient and WebSocket connections via callbacks.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from brokers.common.core.auth import AuthManager

logger = logging.getLogger(__name__)

# Default refresh interval: 20 minutes
_DEFAULT_INTERVAL_SECONDS = 20 * 60

# Default buffer: refresh when 10 minutes remain
_DEFAULT_BUFFER_SECONDS = 600


class TokenRefreshScheduler:
    """Background scheduler that proactively refreshes broker tokens.

    Usage::
        auth = AuthManager(...)
        scheduler = TokenRefreshScheduler(auth, on_refresh=my_update_fn)
        scheduler.start()
        # ... later ...
        scheduler.stop()
    """

    def __init__(
        self,
        auth: AuthManager,
        interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
        buffer_seconds: float = _DEFAULT_BUFFER_SECONDS,
        on_refresh: Callable[[str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        """
        Args:
            auth: AuthManager instance for token lifecycle.
            interval_seconds: How often to check token validity (default 20 min).
            buffer_seconds: How far before expiry to proactively refresh (default 10 min).
            on_refresh: Called with the new access_token string after a successful refresh.
            on_error: Called if refresh fails.
        """
        self._auth = auth
        self._interval = interval_seconds
        self._buffer = buffer_seconds
        self._on_refresh = on_refresh
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_count = 0

    def start(self) -> None:
        """Start the background refresh thread."""
        if self._thread and self._thread.is_alive():
            logger.debug("Token refresh scheduler already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="token-refresh")
        self._thread.start()
        logger.info(
            "Token refresh scheduler started (interval=%ds, buffer=%.0fs)",
            self._interval,
            self._buffer,
        )

    def stop(self) -> None:
        """Stop the background refresh thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Token refresh scheduler stopped (refreshed %d times)", self._refresh_count)

    def refresh_now(self) -> bool:
        """Trigger an immediate refresh check. Returns True if refreshed."""
        return self._do_refresh()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    def _run(self) -> None:
        """Background loop that checks token validity periodically."""
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as exc:
                logger.error("Token refresh scheduler error: %s", exc)
                if self._on_error:
                    try:
                        self._on_error(exc)
                    except Exception:
                        pass
            # Wait for next interval or stop signal
            self._stop_event.wait(timeout=self._interval)

    def _do_refresh(self) -> bool:
        """Check token validity and refresh if needed. Returns True if refreshed.

        Uses the factory's token refresh lock to prevent concurrent refresh
        with the HTTP 401 handler.
        """
        try:
            # Import the lock from factory to coordinate with HTTP refresh
            from brokers.dhan.factory import _token_refresh_lock

            if not _token_refresh_lock.acquire(blocking=False):
                # Another refresh is already in progress
                logger.debug("Token refresh already in progress (from HTTP handler), skipping scheduler refresh")
                return False
            try:
                if self._auth.ensure_valid(buffer_seconds=self._buffer):
                    # Check if a new token was actually issued
                    state = self._auth.state
                    if state and self._on_refresh:
                        self._on_refresh(state.access_token)
                    self._refresh_count += 1
                    logger.debug("Token refresh check passed (count=%d)", self._refresh_count)
                    return True
                else:
                    logger.warning("Token refresh check failed — no valid token available")
                    return False
            finally:
                _token_refresh_lock.release()
        except Exception as exc:
            logger.warning("Token refresh failed: %s", exc)
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception:
                    pass
            return False
