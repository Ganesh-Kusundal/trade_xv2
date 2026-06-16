"""Sync HTTP client for Dhan REST API with token refresh, retry, and logging."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitState
from brokers.dhan.exceptions import AuthenticationError, DhanError, RateLimitError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.dhan.co/v2"

# Per-endpoint minimum interval (seconds) — matches Dhan documented rate limits
# Non-Trading APIs: Up to 20 requests per second
# Order APIs: Up to 25 requests per second
# Data APIs: Up to 10 requests per second
# Quote APIs: 1 request per second (we use 0.15s for safety)
_RATE_LIMITS: dict[str, float] = {
    "/marketfeed/quote": 0.15,  # 1 req/s documented, using 0.15s for safety
    "/marketfeed/ltp": 0.15,    # 10 req/s documented
    "/marketfeed/ohlc": 0.15,   # 10 req/s documented
    "/optionchain": 0.35,       # 10 req/s documented
    "/charts/": 0.15,           # 10 req/s documented
    "/orders": 0.04,            # 25 req/s documented
}

# Retry configuration
_MAX_RETRIES = 3
_BASE_DELAY_MS = 500
_MAX_DELAY_MS = 5000
_REFRESH_COOLDOWN_SECONDS = 60

# ── Endpoint categorization for circuit-breaker isolation (A1) ────────────
#
# Previously a single `CircuitBreaker("dhan-api")` protected every endpoint.
# That meant a storm of failed historical-data reads (or option-chain calls)
# would OPEN the breaker and block order placement. Phase A / A1 splits the
# breaker into three categories so a failure in one class cannot take down
# another:
#
#   READ   — market data; no user state change.  Most bursty, most likely
#            to hit rate limits; failure here must NOT block orders.
#   WRITE  — order placement, modification, cancellation. User money is on
#            the line. The most sensitive category; opened quickly.
#   ADMIN  — account state queries (positions/holdings/funds/orderbook/
#            tradebook), broker auth (token refresh), kill switch. Default
#            category for unrecognised endpoints.
#
# Endpoints are matched by `endpoint.startswith(prefix)` so `/charts/historical`
# matches the prefix `/charts/`. Unknown endpoints default to ADMIN.
_READ_CB_PREFIXES: tuple[str, ...] = (
    "/marketfeed/ltp",
    "/marketfeed/quote",
    "/marketfeed/ohlc",
    "/charts/",
    "/optionchain",
    "/marketstatus",
    "/instruments",
)
_WRITE_CB_PREFIXES: tuple[str, ...] = (
    "/orders",  # POST/PUT/DELETE on /orders is a write; the GET orderbook
    # is also matched here, but the factory wires the read category to a
    # higher threshold. We accept the slight imprecision — orderbook
    # reads are rare on the hot path and the admin CB's threshold still
    # protects against runaway 5xx storms.
    "/killswitch",  # PUT /killswitch mutates broker session state
    "/sliceorder",
)
# Note: /traderbook and /trades are intentionally NOT in the write list.
# They are account-state reads; the categorization defaults them to
# "admin" so they share the admin CB with /positions, /holdings,
# /fundlimit, /traderbook. This keeps the orderbook failure mode
# isolated from order placement.


def _categorize_endpoint(endpoint: str) -> str:
    """Return one of 'read', 'write', or 'admin' for an endpoint path.

    Used by ``DhanHttpClient._get_circuit_breaker`` to route failures to
    the category-specific circuit breaker.
    """
    for prefix in _WRITE_CB_PREFIXES:
        if endpoint.startswith(prefix):
            return "write"
    for prefix in _READ_CB_PREFIXES:
        if endpoint.startswith(prefix):
            return "read"
    return "admin"


class DhanHttpClient:
    """Sync HTTP client with auth injection, token refresh, retry, and rate limiting."""

    def __init__(
        self,
        client_id: str,
        access_token: str,
        base_url: str = _BASE_URL,
        timeout: float = 15.0,
        token_refresh_fn: Callable[[], str] | None = None,
        enable_retry: bool = True,
        circuit_breaker: CircuitBreaker | None = None,
        read_circuit_breaker: CircuitBreaker | None = None,
        write_circuit_breaker: CircuitBreaker | None = None,
        admin_circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.client_id = client_id
        self.access_token = access_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._token_refresh_fn = token_refresh_fn
        self._enable_retry = enable_retry
        # Backwards-compat: a single ``circuit_breaker`` is used for any
        # category whose specific CB was not provided. This keeps every
        # existing test fixture working unchanged.
        self._circuit_breaker = circuit_breaker
        self._read_circuit_breaker = read_circuit_breaker or circuit_breaker
        self._write_circuit_breaker = write_circuit_breaker or circuit_breaker
        self._admin_circuit_breaker = admin_circuit_breaker or circuit_breaker
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "client-id": client_id,
            "access-token": access_token,
        })
        self._last_request_time: dict[str, float] = {}
        self._rate_lock = threading.Lock()
        self._last_refresh_time: float = 0.0

    def _get_circuit_breaker(self, endpoint: str) -> CircuitBreaker | None:
        """Return the circuit breaker that protects ``endpoint``.

        Routes to the category-specific CB if one was supplied;
        otherwise falls back to the single ``circuit_breaker`` argument
        (backwards-compat path).
        """
        category = _categorize_endpoint(endpoint)
        if category == "read":
            return self._read_circuit_breaker
        if category == "write":
            return self._write_circuit_breaker
        return self._admin_circuit_breaker

    def update_token(self, access_token: str) -> None:
        self.access_token = access_token
        self._session.headers["access-token"] = access_token

    def post(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json)

    def get(self, endpoint: str) -> dict[str, Any]:
        return self._request("GET", endpoint)

    def put(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return self._request("PUT", endpoint, json=json)

    def delete(self, endpoint: str) -> dict[str, Any]:
        return self._request("DELETE", endpoint)

    def _throttle(self, endpoint: str) -> None:
        min_interval = _RATE_LIMITS.get(endpoint)
        if min_interval is None:
            return
        with self._rate_lock:
            last = self._last_request_time.get(endpoint, 0.0)
            elapsed = time.time() - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request_time[endpoint] = time.time()

    def _try_refresh_token(self) -> bool:
        """Attempt token refresh. Returns True if successful."""
        now = time.time()
        if now - self._last_refresh_time < _REFRESH_COOLDOWN_SECONDS:
            logger.debug("token_refresh_skipped", extra={"reason": "cooldown_active"})
            return False
        if self._token_refresh_fn is None:
            return False
        try:
            self._last_refresh_time = now
            new_token = self._token_refresh_fn()
            if new_token:
                self.update_token(new_token)
                logger.info("token_refreshed", extra={"client_id": self.client_id})
                return True
        except Exception as exc:
            logger.warning("token_refresh_failed", extra={"error": str(exc)})
        return False

    def _request(self, method: str, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        # Circuit breaker check — fast-fail if the category-specific
        # breaker for this endpoint is OPEN. The split (read / write /
        # admin) is what stops a read-side failure storm from blocking
        # order placement. See PRODUCTION_CERTIFICATION_REPORT §B1.
        cb = self._get_circuit_breaker(endpoint)
        if cb and cb.state == CircuitState.OPEN:
            if not cb.allow_request():
                raise DhanError(f"Circuit breaker open: {method} {endpoint}")

        self._throttle(endpoint)
        url = f"{self._base_url}{endpoint}" if endpoint.startswith("/") else endpoint

        max_attempts = _MAX_RETRIES if self._enable_retry else 1
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._session.request(method, url, json=json, timeout=self._timeout)
            except requests.RequestException as exc:
                last_exc = DhanError(f"HTTP {method} {url} failed: {exc}")
                if cb:
                    cb.on_failure()
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
                    logger.warning("http_retry", extra={
                        "method": method, "endpoint": endpoint, "attempt": attempt, "delay_ms": int(delay * 1000),
                    })
                    time.sleep(delay)
                    continue
                raise last_exc from exc

            logger.debug("http_response", extra={
                "method": method, "endpoint": endpoint, "status": resp.status_code,
            })

            # 401 — try token refresh
            if resp.status_code == 401:
                if attempt == 1 and self._try_refresh_token():
                    logger.info("http_retry_after_refresh", extra={"method": method, "endpoint": endpoint})
                    continue  # retry with new token
                raise AuthenticationError(f"Token rejected: HTTP 401 on {method} {endpoint}")

            # 429 — rate limited, back off and retry
            if resp.status_code == 429:
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
                    logger.warning("http_rate_limited_retry", extra={
                        "method": method, "endpoint": endpoint, "attempt": attempt, "delay_ms": int(delay * 1000),
                    })
                    time.sleep(delay)
                    continue
                raise RateLimitError(f"Rate limited: HTTP 429 on {method} {endpoint}")

            # 5xx — server error, retry
            if resp.status_code >= 500:
                if cb:
                    cb.on_failure()
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
                    logger.warning("http_server_error_retry", extra={
                        "method": method, "endpoint": endpoint, "status": resp.status_code,
                        "attempt": attempt, "delay_ms": int(delay * 1000),
                    })
                    time.sleep(delay)
                    continue
                body = resp.text[:200]
                raise DhanError(f"Dhan API {method} {url} failed: HTTP {resp.status_code} — {body}")

            # 4xx — check for Dhan-specific token errors (DH-906/DH-808 returned as 400)
            if resp.status_code >= 400:
                body = resp.text[:300]
                # Dhan returns invalid token as HTTP 400 with DH-906 or DH-808
                if resp.status_code == 400 and ("DH-906" in body or "DH-808" in body or "Invalid Token" in body):
                    if attempt == 1 and self._try_refresh_token():
                        logger.info("http_retry_after_token_refresh", extra={"method": method, "endpoint": endpoint})
                        continue
                    raise AuthenticationError(f"Token rejected: DH-906 on {method} {endpoint}")
                logger.warning("http_client_error", extra={
                    "method": method, "endpoint": endpoint, "status": resp.status_code, "body": body,
                })
                raise DhanError(f"Dhan API {method} {url} failed: HTTP {resp.status_code} — {body}")

            # Success
            try:
                data = resp.json()
            except Exception as exc:
                raise DhanError(f"Invalid JSON from {method} {url}") from exc

            if isinstance(data, dict) and data.get("status") == "failure":
                remarks = data.get("remarks", "unknown error")
                if cb:
                    cb.on_failure()
                raise DhanError(f"API failure: {remarks}")

            if cb:
                cb.on_success()
            return data

        # Should not reach here, but just in case
        if last_exc:
            raise last_exc
        raise DhanError(f"Request failed after {max_attempts} attempts: {method} {url}")

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Exponential backoff: 500ms, 1s, 2s, 4s... capped at 5s."""
        delay_ms = min(_BASE_DELAY_MS * (2 ** (attempt - 1)), _MAX_DELAY_MS)
        return delay_ms / 1000.0

    def close(self) -> None:
        self._session.close()
