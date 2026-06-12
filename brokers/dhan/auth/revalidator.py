"""Background Dhan token revalidation against /v2/profile.

Design reference: Trade_J ``DhanTokenRevalidator``.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from brokers.dhan.auth.auth import DhanAuthClient, DhanHttpError, DhanTokenManager

if TYPE_CHECKING:
    from brokers.dhan.auth.config import DhanConnectionSettings

logger = logging.getLogger(__name__)

TOKEN_REVALIDATION_INTERVAL_MS = 5 * 60 * 1000


class DhanTokenRevalidator:
    """Periodic profile sync to detect broker-side token revocation early."""

    def __init__(
        self,
        token_manager: DhanTokenManager,
        auth_client: DhanAuthClient,
        settings: DhanConnectionSettings,
        *,
        interval_ms: int = TOKEN_REVALIDATION_INTERVAL_MS,
    ) -> None:
        self._token_manager = token_manager
        self._auth_client = auth_client
        self._settings = settings
        self._interval_ms = interval_ms
        self._timer: threading.Timer | None = None
        self._shutdown = False
        self._last_run_at_ms = 0

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    @property
    def last_run_at_ms(self) -> int:
        return self._last_run_at_ms

    def is_running(self) -> bool:
        return self._timer is not None and not self._shutdown

    def start(self) -> None:
        if self._shutdown:
            logger.warning("DhanTokenRevalidator.start() called after shutdown")
            return
        if self._timer is not None:
            return
        self._shutdown = False
        self._schedule_next(initial_delay_ms=self._interval_ms)
        logger.info("DhanTokenRevalidator started — interval=%sms", self._interval_ms)

    def stop(self) -> None:
        self._shutdown = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("DhanTokenRevalidator stopped")

    def close(self) -> None:
        self.stop()

    def run_once(self) -> bool:
        """Run a single revalidation cycle (for tests and manual triggers)."""
        import time

        self._last_run_at_ms = int(time.time() * 1000)
        state = self._token_manager.current_snapshot()
        if not state or not state.access_token:
            return False
        try:
            info = self._auth_client.fetch_profile(
                state.access_token, self._settings.refresh_buffer_minutes * 60_000
            )
            if info.valid and not info.refresh_recommended:
                return self._token_manager.update_cached_expiry(info.expiry_epoch_ms)
            logger.warning(
                "Dhan /v2/profile reported token no longer fresh — invalidating cached state"
            )
            self._token_manager.invalidate()
            return False
        except DhanHttpError as exc:
            if exc.status_code in {400, 401}:
                logger.warning(
                    "Dhan /v2/profile rejected cached token (HTTP %s): invalidating",
                    exc.status_code,
                )
                self._token_manager.invalidate()
            else:
                logger.debug(
                    "Dhan /v2/profile HTTP error (HTTP %s): keeping cached token",
                    exc.status_code,
                )
            return False
        except Exception as exc:
            logger.debug("Dhan /v2/profile unexpected error: %s", exc)
            return False

    def _schedule_next(self, *, initial_delay_ms: int | None = None) -> None:
        if self._shutdown:
            return
        delay_s = (initial_delay_ms or self._interval_ms) / 1000.0
        self._timer = threading.Timer(delay_s, self._run_cycle)
        self._timer.daemon = True
        self._timer.start()

    def _run_cycle(self) -> None:
        if self._shutdown:
            return
        try:
            self.run_once()
        except Exception as exc:
            logger.warning("DhanTokenRevalidator cycle failed: %s", exc)
        finally:
            self._timer = None
            self._schedule_next()
