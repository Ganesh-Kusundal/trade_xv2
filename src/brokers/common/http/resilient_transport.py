"""Shared resilient HTTP transport for broker clients (DP-01)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EndpointPolicy:
    """Rate-limit bucket key for a request class."""

    bucket: str = "default"
    is_write: bool = False


class ResilientHttpTransport:
    """Circuit-breaker + rate-limiter + retry shell for sync HTTP."""

    def __init__(
        self,
        *,
        rate_limiter: Any | None = None,
        circuit_breaker: Any | None = None,
        retry_policy: Callable[[int, Exception], bool] | None = None,
    ) -> None:
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy or (lambda status, _exc: status >= 500)

    def acquire_token(self, policy: EndpointPolicy) -> None:
        if self._rate_limiter is not None and hasattr(self._rate_limiter, "acquire"):
            self._rate_limiter.acquire(policy.bucket)

    def before_request(self, policy: EndpointPolicy) -> None:
        if self._circuit_breaker is not None and hasattr(self._circuit_breaker, "before_call"):
            self._circuit_breaker.before_call()
        self.acquire_token(policy)

    def after_success(self) -> None:
        if self._circuit_breaker is not None and hasattr(self._circuit_breaker, "on_success"):
            self._circuit_breaker.on_success()

    def after_failure(self, exc: Exception) -> None:
        if self._circuit_breaker is not None and hasattr(self._circuit_breaker, "on_failure"):
            self._circuit_breaker.on_failure(exc)

    def should_retry(self, status_code: int, exc: Exception, attempt: int, max_attempts: int) -> bool:
        if attempt >= max_attempts:
            return False
        return self._retry_policy(status_code, exc)
