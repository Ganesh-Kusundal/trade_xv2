"""Daily PnL reset scheduler.

Phase A / A2: this is the missing piece in the previous implementation.
``RiskManager._daily_pnl`` accumulated without ever being reset, so a
process running across the IST 00:00 boundary carried yesterday's loss
into today's order checks.

The scheduler is a :class:`ManagedService` that:

1. Wakes up every ``poll_interval_seconds`` (default 60s).
2. Computes the next IST rollover moment relative to ``now``.
3. If the rollover moment has passed since the last reset, calls
   :meth:`RiskManager.reset_daily_pnl`.
4. Records the last reset time so a second pass through the same
   rollover moment does not double-fire.

The rollover hour is configurable (default 00:00 IST) so an institution
that wants to roll over at 03:00 IST can do so. The timezone is fixed
to IST (UTC+5:30) because that is the only relevant trading session
boundary in the current scope.

Lifecycle contract
------------------
The scheduler MUST be registered with a :class:`LifecycleManager` so
shutdown drains it within ``stop(timeout_seconds)``. It MUST NOT be
started as a bare daemon thread — that was the leak the certification
report flagged for ``TokenRefreshScheduler`` and ``ReconciliationService``.
"""

from __future__ import annotations

import logging
import threading
import time as _time
from datetime import datetime, timedelta, timezone

from domain.constants import (
    DAILY_PNL_POLL_INTERVAL_SECONDS,
    DAILY_PNL_ROLLOVER_HOUR_IST,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    IST_OFFSET,
)
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
    now_monotonic,
)
from application.oms.risk_manager import RiskManager

logger = logging.getLogger(__name__)

# IST is UTC+5:30 with no daylight savings. Use a fixed offset to avoid
# pulling in pytz / zoneinfo as a runtime dependency.
_IST = IST_OFFSET

_DEFAULT_POLL_INTERVAL_SECONDS = DAILY_PNL_POLL_INTERVAL_SECONDS
_DEFAULT_ROLLOVER_HOUR_IST = DAILY_PNL_ROLLOVER_HOUR_IST


class DailyPnlResetScheduler(ManagedService):
    """Periodically reset the daily PnL on :class:`RiskManager`.

    Parameters
    ----------
    risk_manager:
        The :class:`RiskManager` whose :meth:`reset_daily_pnl` will be
        called. The scheduler holds a reference for the duration of its
        lifetime; the caller is responsible for ensuring the manager
        outlives the scheduler.
    rollover_hour_ist:
        Hour-of-day in IST at which the daily PnL is reset. Default 0
        (midnight IST). Allowed range 0-23.
    poll_interval_seconds:
        How often the scheduler thread wakes up to check the rollover
        boundary. Default 60s. Lower values reduce the worst-case
        latency between rollover and reset.
    """

    name = "daily-pnl-reset"

    def __init__(
        self,
        risk_manager: RiskManager,
        rollover_hour_ist: int = _DEFAULT_ROLLOVER_HOUR_IST,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        if not 0 <= rollover_hour_ist <= 23:
            raise ValueError(
                f"rollover_hour_ist must be in 0..23, got {rollover_hour_ist}"
            )
        if poll_interval_seconds <= 0:
            raise ValueError(
                f"poll_interval_seconds must be positive, got {poll_interval_seconds}"
            )
        self._risk_manager = risk_manager
        self._rollover_hour = rollover_hour_ist
        self._poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # The last rollover moment (as a Unix timestamp) we already
        # fired on. Used to prevent double-firing if the loop iterates
        # more than once within the same rollover window.
        self._last_reset_unix: float = 0.0
        # Monotonic counters for health().
        self._reset_count: int = 0
        self._last_error: str | None = None
        self._start_time_monotonic: float = 0.0

    # ── ManagedService protocol ─────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler thread. Idempotent."""
        if self._thread and self._thread.is_alive():
            logger.debug("daily_pnl_reset_scheduler_already_running")
            return
        self._stop_event.clear()
        self._start_time_monotonic = now_monotonic()
        # Initialise _last_reset_unix to the last rollover moment so
        # the first reset fires the first time we cross the boundary
        # after start.
        self._last_reset_unix = self._last_rollover_unix(_time.time())
        self._thread = threading.Thread(
            target=self._run,
            name="daily-pnl-reset",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "daily_pnl_reset_scheduler_started",
            extra={"poll_interval_s": self._poll_interval},
        )

    def stop(self, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        """Stop the scheduler thread. Idempotent. Joins within timeout."""
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            logger.warning("daily_pnl_reset_scheduler_stop_timeout")
        else:
            logger.info("daily_pnl_reset_scheduler_stopped")
        self._thread = None

    def health(self) -> HealthStatus:
        """Return the current health snapshot."""
        if self._last_error and not self._thread:
            return HealthStatus(
                state=HealthState.FAILED,
                service=self.name,
                last_check=datetime.now(_IST),
                detail=self._last_error,
                metrics=self._metrics(),
            )
        if self._thread and self._thread.is_alive():
            state = HealthState.HEALTHY
            detail = "running"
        else:
            state = HealthState.STOPPED
            detail = "not started"
        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(_IST),
            detail=detail,
            metrics=self._metrics(),
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _metrics(self) -> dict:
        return {
            "reset_count": self._reset_count,
            "rollover_hour_ist": self._rollover_hour,
            "poll_interval_seconds": self._poll_interval,
            "seconds_since_start": (
                now_monotonic() - self._start_time_monotonic
                if self._start_time_monotonic > 0
                else 0.0
            ),
        }

    def _run(self) -> None:
        """Main scheduler loop.

        Uses ``Event.wait(timeout)`` so a stop request is honored
        immediately, even if ``_poll_interval`` is large.
        """
        try:
            while not self._stop_event.is_set():
                try:
                    self._maybe_reset()
                except Exception as exc:  # pragma: no cover - defensive
                    self._last_error = str(exc)
                    logger.exception("daily_pnl_reset_iteration_failed")
                # Interruptible sleep.
                if self._stop_event.wait(timeout=self._poll_interval):
                    break
        finally:
            logger.debug("daily_pnl_reset_scheduler_thread_exiting")

    def _maybe_reset(self) -> None:
        """If a new rollover moment has passed, reset the daily PnL."""
        now_unix = _time.time()
        last_rollover = self._last_rollover_unix(now_unix)
        if last_rollover > self._last_reset_unix:
            # The boundary has been crossed since the last reset.
            self._risk_manager.reset_daily_pnl()
            self._last_reset_unix = last_rollover
            self._reset_count += 1
            self._last_error = None
            logger.info(
                "daily_pnl_reset_fired",
                extra={
                    "rollover_unix": last_rollover,
                    "reset_count": self._reset_count,
                },
            )

    def _last_rollover_unix(self, now_unix: float) -> float:
        """Return the Unix timestamp of the most recent rollover moment
        (``rollover_hour_ist`` in IST) at or before ``now_unix``.

        Examples (rollover_hour_ist=0, i.e. IST midnight):
          - now = 2026-06-15 18:30 UTC  (= 2026-06-16 00:00 IST)
            returns 2026-06-15 18:30 UTC
          - now = 2026-06-15 18:29 UTC  (= 2026-06-15 23:59 IST)
            returns 2026-06-14 18:30 UTC
        """
        now_ist = datetime.fromtimestamp(now_unix, tz=_IST)
        rollover_today_ist = now_ist.replace(
            hour=self._rollover_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        if now_ist >= rollover_today_ist:
            return rollover_today_ist.timestamp()
        # Roll back one day.
        return (rollover_today_ist - timedelta(days=1)).timestamp()
