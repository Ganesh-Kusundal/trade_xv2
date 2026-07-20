"""Backoff strategies for retry with exponential backoff + jitter.

Maps 1:1 to Trade_J's BackoffStrategy pattern.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from domain.constants import (
    BACKOFF_JITTER,
    BACKOFF_MULTIPLIER,
    MAX_RETRY_DELAY_MS,
    RETRY_BASE_DELAY_MS,
)


class BackoffStrategy(ABC):
    """Abstract strategy for computing retry delays."""

    @abstractmethod
    def delay(self, attempt: int) -> float:
        """Return the delay in seconds before the given attempt number."""
        ...

    def reset(self) -> None:
        """Reset any internal state."""
        return None


class ExponentialBackoff(BackoffStrategy):
    """Exponential backoff with jitter.

    delay = min(base * multiplier^attempt + jitter, max_delay)
    """

    def __init__(
        self,
        base_delay_ms: float = RETRY_BASE_DELAY_MS,
        max_delay_ms: float = MAX_RETRY_DELAY_MS,
        multiplier: float = BACKOFF_MULTIPLIER,
        jitter_factor: float = BACKOFF_JITTER,
    ):
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._multiplier = multiplier
        self._jitter_factor = jitter_factor

    def delay(self, attempt: int) -> float:
        raw_delay = self._base_delay_ms * (self._multiplier**attempt)
        capped_delay = min(raw_delay, self._max_delay_ms)

        # Add jitter: ±jitter_factor% of the capped delay
        jitter = capped_delay * self._jitter_factor * (2 * random.random() - 1)
        delay_ms = capped_delay + jitter
        delay_ms = max(delay_ms, 0.0)
        delay_ms = min(delay_ms, self._max_delay_ms)

        return delay_ms / 1000.0


def exponential_backoff_seconds(
    attempt: int,
    base_delay_ms: float = 500.0,
    max_delay_ms: float = 5000.0,
) -> float:
    """Simple exponential backoff in seconds (HTTP client helper)."""
    delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
    return delay_ms / 1000.0
