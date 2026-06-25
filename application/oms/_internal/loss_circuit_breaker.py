"""Loss-based circuit breaker for trading halts.

Trips when cumulative losses within a rolling window exceed a configured
percentage of capital. Provides observable state, manual reset, and
automatic cooldown recovery.

Design decisions
----------------
- **Percentage-based** (not absolute INR) — adapts to account size changes.
- **Rolling 24h window** — catches sustained loss patterns across days.
- **30-min cooldown** — prevents immediate re-entry after trip; operators
  must consciously re-enable trading.
- **Independent of kill_switch** — maintains its own state so a reset of
  one does not silently reset the other.
- **Manual + automatic reset** — operators can override after review;
  cooldown expires automatically to CLOSED.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from domain.constants import (
    RISK_LOSS_CB_COOLDOWN_SECONDS,
    RISK_LOSS_CB_WINDOW_SECONDS,
    RISK_LOSS_CIRCUIT_BREAKER_PERCENT,
)

logger = logging.getLogger(__name__)


class LossCircuitState(str, Enum):
    """State of the loss-based circuit breaker."""

    CLOSED = "CLOSED"  # Trading allowed; losses within threshold.
    OPEN = "OPEN"  # Trading halted; losses exceeded threshold.
    COOLDOWN = "COOLDOWN"  # Post-trip cooling period; auto-transitions to CLOSED.


@dataclass(frozen=True)
class LossCircuitBreakerConfig:
    """Configuration for the loss-based circuit breaker."""

    loss_threshold_pct: Decimal = Decimal(str(RISK_LOSS_CIRCUIT_BREAKER_PERCENT))
    """Cumulative loss as a percentage of capital that triggers the circuit."""

    cooldown_seconds: int = RISK_LOSS_CB_COOLDOWN_SECONDS
    """Seconds the circuit stays in COOLDOWN before auto-transitioning to CLOSED."""

    window_seconds: int = RISK_LOSS_CB_WINDOW_SECONDS
    """Rolling window in seconds; samples older than this are purged."""

    def __post_init__(self) -> None:
        if self.loss_threshold_pct <= 0:
            raise ValueError(f"loss_threshold_pct must be positive, got {self.loss_threshold_pct}")
        if self.cooldown_seconds <= 0:
            raise ValueError(f"cooldown_seconds must be positive, got {self.cooldown_seconds}")
        if self.window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {self.window_seconds}")


@dataclass
class LossCircuitSample:
    """A single PnL sample recorded at a point in time."""

    timestamp: float  # time.time() when the sample was recorded.
    loss: Decimal  # Negative for loss, positive for gain.
    capital: Decimal  # Capital at the time of recording.


class LossCircuitBreaker:
    """Loss-based circuit breaker with rolling window.

    Records PnL samples and trips to OPEN when the cumulative loss within
    the rolling window exceeds *loss_threshold_pct* of the **most recent**
    capital value.

    Thread safety
    -------------
    All mutable state is protected by an ``RLock``. ``record_loss`` and
    ``allow_trading`` may be called concurrently from multiple threads.

    Lifecycle
    ---------
    CLOSED -> OPEN   when cumulative loss >= threshold
    OPEN -> COOLDOWN  on ``reset()`` or automatically when losses recover
    COOLDOWN -> CLOSED automatically after ``cooldown_seconds`` elapse
    """

    def __init__(self, config: LossCircuitBreakerConfig | None = None) -> None:
        self.config = config or LossCircuitBreakerConfig()
        self._lock = threading.RLock()
        self._state: LossCircuitState = LossCircuitState.CLOSED
        self._samples: list[LossCircuitSample] = []
        self._opened_at: float = 0.0  # time.time() when circuit opened
        self._cooldown_started_at: float = 0.0  # time.time() when cooldown started
        self._trip_count: int = 0  # monotonic counter of trips to OPEN

    # -- Public API --

    def record_loss(self, loss: Decimal, capital: Decimal) -> None:
        """Record a PnL sample.

        A negative *loss* represents a monetary loss; positive represents
        a gain. The sample is appended to the rolling window. If cumulative
        loss within the window exceeds the configured threshold, the circuit
        transitions to OPEN.

        Parameters
        ----------
        loss:
            PnL delta (negative = loss, positive = gain).
        capital:
            Available capital at the time of recording.
        """
        with self._lock:
            sample = LossCircuitSample(
                timestamp=time.time(),
                loss=loss,
                capital=capital,
            )
            self._samples.append(sample)
            self._purge_old_samples(sample.timestamp)

            if self._state == LossCircuitState.CLOSED:
                cumulative = self._cumulative_loss()
                if capital > 0 and cumulative < 0:
                    loss_pct = abs(cumulative) / capital * 100
                    if loss_pct >= self.config.loss_threshold_pct:
                        self._transition_to(LossCircuitState.OPEN)
                        logger.warning(
                            "loss_circuit_breaker_open",
                            extra={
                                "cumulative_loss": str(cumulative),
                                "capital": str(capital),
                                "loss_pct": str(loss_pct),
                                "threshold_pct": str(self.config.loss_threshold_pct),
                                "trip_count": self._trip_count,
                            },
                        )
            elif self._state == LossCircuitState.OPEN:
                # Check if losses have recovered below threshold due to
                # purging of old samples or new gains.
                cumulative = self._cumulative_loss()
                if capital > 0 and (
                    cumulative >= 0
                    or abs(cumulative) / capital * 100 < self.config.loss_threshold_pct
                ):
                    self._transition_to(LossCircuitState.COOLDOWN)
                    logger.info(
                        "loss_circuit_breaker_auto_recovery",
                        extra={
                            "cumulative_loss": str(cumulative),
                            "capital": str(capital),
                        },
                    )

    def allow_trading(self) -> tuple[bool, str | None]:
        """Check whether trading is currently allowed.

        Returns
        -------
        allowed:
            True if trading may proceed.
        reason:
            Human-readable reason when ``allowed`` is False.
        """
        with self._lock:
            self._maybe_transition_cooldown()
            self._maybe_transition_open_recovery()

            if self._state == LossCircuitState.CLOSED:
                return True, None

            if self._state == LossCircuitState.OPEN:
                return False, "Loss circuit breaker is OPEN — cumulative losses exceeded threshold"

            # COOLDOWN
            return False, (
                f"Loss circuit breaker in COOLDOWN — {self._cooldown_remaining()}s remaining"
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker.

        Transitions OPEN -> COOLDOWN (so operators must still wait for
        cooldown) or COOLDOWN -> CLOSED (immediate re-enable).
        CLOSED is a no-op.
        """
        with self._lock:
            if self._state == LossCircuitState.OPEN:
                self._transition_to(LossCircuitState.COOLDOWN)
                logger.info(
                    "loss_circuit_breaker_manual_reset_to_cooldown",
                    extra={"trip_count": self._trip_count},
                )
            elif self._state == LossCircuitState.COOLDOWN:
                self._transition_to(LossCircuitState.CLOSED)
                logger.info("loss_circuit_breaker_cooldown_cleared")
            # CLOSED: no-op

    def snapshot(self) -> dict:
        """Return a JSON-serializable view of circuit breaker state.

        Useful for ``/healthz`` endpoints and SRE dashboards.
        """
        with self._lock:
            self._maybe_transition_cooldown()
            now = time.time()
            cumulative = self._cumulative_loss()
            window_samples = len(self._samples)

            result: dict = {
                "state": self._state.value,
                "loss_threshold_pct": str(self.config.loss_threshold_pct),
                "cumulative_loss": str(cumulative),
                "window_samples": window_samples,
                "window_seconds": self.config.window_seconds,
                "trip_count": self._trip_count,
            }

            if self._state == LossCircuitState.OPEN:
                result["opened_at"] = self._opened_at
                result["seconds_since_open"] = (
                    now - self._opened_at if self._opened_at > 0 else None
                )

            if self._state == LossCircuitState.COOLDOWN:
                result["cooldown_started_at"] = self._cooldown_started_at
                result["cooldown_remaining_seconds"] = self._cooldown_remaining()

            return result

    # -- Internal helpers (caller must hold _lock) --

    def _transition_to(self, new_state: LossCircuitState) -> None:
        """Transition to a new state. Caller MUST hold ``_lock``."""
        if self._state != new_state:
            previous = self._state.value
            self._state = new_state
            now = time.time()
            if new_state == LossCircuitState.OPEN:
                self._opened_at = now
                self._trip_count += 1
            if new_state == LossCircuitState.COOLDOWN:
                self._cooldown_started_at = now
            logger.debug(
                "loss_circuit_state_change",
                extra={"previous": previous, "new": new_state.value},
            )

    def _purge_old_samples(self, now: float) -> None:
        """Remove samples older than the rolling window. Caller must hold ``_lock``."""
        cutoff = now - self.config.window_seconds
        self._samples = [s for s in self._samples if s.timestamp >= cutoff]

    def _cumulative_loss(self) -> Decimal:
        """Sum of all loss values in the current window. Caller must hold ``_lock``."""
        total = Decimal("0")
        for s in self._samples:
            total += s.loss
        return total

    def _maybe_transition_open_recovery(self) -> None:
        """Auto-transition OPEN -> COOLDOWN if losses have recovered below threshold. Caller must hold ``_lock``."""
        if self._state == LossCircuitState.OPEN and self._samples:
            latest_capital = self._samples[-1].capital
            cumulative = self._cumulative_loss()
            if latest_capital > 0 and (
                cumulative >= 0
                or abs(cumulative) / latest_capital * 100 < self.config.loss_threshold_pct
            ):
                self._transition_to(LossCircuitState.COOLDOWN)
                logger.info(
                    "loss_circuit_breaker_auto_recovery",
                    extra={
                        "cumulative_loss": str(cumulative),
                        "capital": str(latest_capital),
                    },
                )

    def _maybe_transition_cooldown(self) -> None:
        """Auto-transition COOLDOWN -> CLOSED if cooldown has elapsed. Caller must hold ``_lock``."""
        if self._state == LossCircuitState.COOLDOWN:
            elapsed = time.time() - self._cooldown_started_at
            if elapsed >= self.config.cooldown_seconds:
                self._transition_to(LossCircuitState.CLOSED)
                logger.info("loss_circuit_breaker_cooldown_expired_auto_close")

    def _cooldown_remaining(self) -> float:
        """Seconds remaining in cooldown. Caller must hold ``_lock``."""
        if self._state != LossCircuitState.COOLDOWN:
            return 0.0
        elapsed = time.time() - self._cooldown_started_at
        remaining = self.config.cooldown_seconds - elapsed
        return max(0.0, remaining)
