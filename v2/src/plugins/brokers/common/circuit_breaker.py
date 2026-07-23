"""Circuit breaker wrapping HttpClient for fault tolerance."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from plugins.brokers.common.http_client import HttpClient
from shared.errors import NetworkError


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 2


class CircuitBreakerOpenError(RuntimeError, NetworkError):
    """Raised when circuit breaker is open."""


class CircuitBreakerHttpClient:
    """Wraps HttpClient with circuit breaker pattern."""

    def __init__(
        self,
        wrapped: HttpClient,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._success_count = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is open")

        try:
            result = self._wrapped.request(method, url, **kwargs)
            self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        return (time.monotonic() - self._last_failure_time) >= self._config.recovery_timeout

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            else:
                self._failure_count = 0
                self._success_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
                self._last_failure_time = time.monotonic()
            else:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                if self._failure_count >= self._config.failure_threshold:
                    self._state = CircuitState.OPEN
