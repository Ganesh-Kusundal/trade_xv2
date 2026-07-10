"""ResiliencePolicy — declarative reconnect/backoff policy for broker transports.

Defaults come from ``domain.constants.resilience``. Per-broker overrides are
injected at construction (Upstox SDK: interval=10s, max_retries=3; Dhan WS:
max_retries=50 with 429 cooloff).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from domain.constants.resilience import (
    BACKOFF_JITTER,
    BACKOFF_MULTIPLIER,
    MAX_RETRY_ATTEMPTS,
    MAX_RETRY_DELAY_MS,
    RETRY_BASE_DELAY_MS,
)


@dataclass(frozen=True)
class ResiliencePolicy:
    """Immutable reconnect/backoff policy.

    base_delay_s     — initial delay between attempts (seconds).
    max_delay_s      — cap on exponential backoff (seconds).
    max_attempts     — stop after this many failures; <=0 means unlimited.
    multiplier       — exponential growth factor.
    jitter           — ± fraction applied to each delay (0.2 = ±20%).
    cooloff_s        — mandatory pause after rate-limit / max-attempt exhaustion.
    """

    base_delay_s: float = RETRY_BASE_DELAY_MS / 1000.0
    max_delay_s: float = MAX_RETRY_DELAY_MS / 1000.0
    max_attempts: int = MAX_RETRY_ATTEMPTS
    multiplier: float = BACKOFF_MULTIPLIER
    jitter: float = BACKOFF_JITTER
    cooloff_s: float = 60.0

    @classmethod
    def for_upstox_ws(cls) -> ResiliencePolicy:
        """Upstox SDK ``auto_reconnect(True, 10, 3)`` defaults."""
        return cls(base_delay_s=10.0, max_delay_s=300.0, max_attempts=3)

    @classmethod
    def for_dhan_ws(cls) -> ResiliencePolicy:
        """Dhan WS: persistent reconnect with 429 cooloff (no broker-documented cap)."""
        return cls(base_delay_s=1.0, max_delay_s=30.0, max_attempts=50, cooloff_s=60.0)

    @classmethod
    def for_http(cls) -> ResiliencePolicy:
        """HTTP retry — domain resilience defaults (3 attempts)."""
        return cls()

    def should_retry(self, attempt: int) -> bool:
        if self.max_attempts <= 0:
            return True
        return attempt < self.max_attempts

    def delay_for(self, attempt: int, *, with_jitter: bool = True) -> float:
        """Return sleep seconds for the given 0-based failure attempt."""
        raw = self.base_delay_s * (self.multiplier**attempt)
        delay = min(raw, self.max_delay_s)
        if with_jitter and self.jitter > 0:
            delay *= 1.0 + random.uniform(-self.jitter, self.jitter)
        return max(0.0, delay)


__all__ = ["ResiliencePolicy"]
