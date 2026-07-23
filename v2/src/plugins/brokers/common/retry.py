"""HTTP retry policies with exponential backoff."""

from __future__ import annotations

import random
import threading
import time
import urllib.error
from dataclasses import dataclass
from typing import Any

from plugins.brokers.common.http_client import HttpClient
from shared.errors import NetworkError


class RetryExhaustedError(RuntimeError, NetworkError):
    """Raised when all retry attempts are exhausted."""


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for HTTP retry behavior."""

    max_retries: int = 3
    base_delay: float = 0.5  # seconds
    max_delay: float = 10.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_status: tuple[int, ...] = (429, 500, 502, 503, 504)
    # G13: Write-safety guard — only retry writes on definitive 429/5xx, not on timeout
    safe_retry_on_ambiguous_write: bool = False


class RetryableHttpClient:
    """Wraps HttpClient with retry logic and exponential backoff.

    G13: Write-safety guard — when ``is_write`` is True, only retry on
    definitive 429/5xx responses, not on timeout/connection errors.
    """

    def __init__(
        self,
        wrapped: HttpClient,
        config: RetryConfig | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._config = config or RetryConfig()
        self._lock = threading.Lock()

    def request(
        self,
        method: str,
        url: str,
        *,
        is_write: bool = False,
        **kwargs: Any,
    ) -> tuple[int, Any]:
        last_exception: Exception | None = None
        last_status: int | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                status, body = self._wrapped.request(method, url, **kwargs)

                # Check if status is retryable
                if status in self._config.retryable_status:
                    last_status = status
                    if attempt < self._config.max_retries:
                        delay = self._calc_delay(attempt)
                        time.sleep(delay)
                        continue
                    # Last attempt with retryable status
                    raise RetryExhaustedError(
                        f"Retry exhausted after {self._config.max_retries} attempts: HTTP {status}"
                    )

                return status, body

            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                last_exception = e
                # G13: Don't retry ambiguous writes on network errors
                if is_write and not self._config.safe_retry_on_ambiguous_write:
                    raise
                if attempt < self._config.max_retries:
                    delay = self._calc_delay(attempt)
                    time.sleep(delay)
                    continue
            except RetryExhaustedError:
                raise
            except Exception:
                # Non-retryable exceptions (auth errors, etc.)
                raise

        raise RetryExhaustedError(
            f"Retry exhausted after {self._config.max_retries} attempts: {last_exception}"
        )

    def _calc_delay(self, attempt: int) -> float:
        delay = min(
            self._config.base_delay * (self._config.exponential_base**attempt),
            self._config.max_delay,
        )
        if self._config.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay
