"""Authenticated HTTP client for Upstox REST endpoints.

Mirrors Trade_J ``UpstoxHttpClient``: Bearer + optional ``X-Algo-Name`` header
injection. Stateless w.r.t. the algo name — supplied per call.

Now includes circuit breaker and retry patterns for resilience (RES-03, RES-04).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

from infrastructure.resilience.backoff import ExponentialBackoff
from infrastructure.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from infrastructure.resilience.rate_limiter import MultiBucketRateLimiter

from .exceptions import UpstoxApiError, UpstoxAuthError, UpstoxFundsMaintenanceError

logger = logging.getLogger(__name__)


def _is_ambiguous_write(method: str, url: str) -> bool:
    """Order writes must not be auto-retried after ambiguous transport failure."""
    return _categorize_upstox_url(url, method) == "write"


def _categorize_upstox_url(url: str, method: str) -> str:
    """Return 'read', 'write', or 'admin' for Upstox REST URLs."""
    lower = url.lower()
    if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and "/order" in lower:
        return "write"
    if "/market-quote" in lower or "/market/" in lower or "/historical" in lower:
        return "read"
    if "/order" in lower and method.upper() == "GET":
        return "read"
    if "/portfolio" in lower or "/user/" in lower or "/login/" in lower:
        return "admin"
    return "admin"


def _rate_limit_bucket(url: str) -> str:
    """Return the rate-limiter bucket name for an Upstox REST URL.

    Bucket names align with ``upstox_capabilities().rate_limit_profiles``
    endpoint classes: orders, quotes, historical, option_chain, funds,
    positions, holdings, plus catch-all ``admin``.
    """
    lower = url.lower()
    if "/market-quote" in lower or "/market-data" in lower:
        return "quotes"
    if "/option/chain" in lower or "/option-chain" in lower or "option_chain" in lower:
        return "option_chain"
    if "/historical" in lower or "/expired-instruments" in lower:
        return "historical"
    if "/order" in lower or "/gtt" in lower:
        return "orders"
    if "long-term-holdings" in lower or "/holdings" in lower:
        return "holdings"
    if "short-term-positions" in lower or "/positions" in lower:
        return "positions"
    if (
        "get-funds" in lower
        or "/funds" in lower
        or "/charges/margin" in lower
        or "/margins" in lower
    ):
        return "funds"
    # profile, login, convert, payments, kill-switch, IPO, …
    return "admin"


class _UpstoxRateLimitAdapter:
    """Adapt Upstox MultiBucketRateLimiter to ResilientHttpTransport (DP-01)."""

    def __init__(self, client: "UpstoxHttpClient") -> None:
        self._client = client

    def acquire(self, bucket: str, tokens: int = 1, timeout: float = 30.0) -> bool:
        return bool(
            self._client._rate_limiter.acquire(
                bucket, tokens=tokens, timeout=self._client._rate_limit_timeout
            )
        )


class UpstoxHttpClient:
    """Small authenticated HTTP client for Upstox v2 / v3 / HFT endpoints."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        settings: Any,
        *,
        timeout_seconds: int = 15,
        session: requests.Session | None = None,
        rate_limiter: MultiBucketRateLimiter | None = None,
        enable_circuit_breaker: bool = True,
        circuit_breaker: CircuitBreaker | None = None,
        read_circuit_breaker: CircuitBreaker | None = None,
        write_circuit_breaker: CircuitBreaker | None = None,
        admin_circuit_breaker: CircuitBreaker | None = None,
        on_auth_failure: Callable[[], bool] | None = None,
        rate_limit_timeout_seconds: float = 30.0,
        max_retries: int = 3,
        max_backoff_seconds: float = 10.0,
    ) -> None:
        self._token_provider = token_provider
        self._settings = settings
        self._on_auth_failure = on_auth_failure
        self._timeout_seconds = timeout_seconds
        self._rate_limit_timeout = rate_limit_timeout_seconds
        self._max_retries = max_retries
        self._backoff_strategy = ExponentialBackoff(
            base_delay_ms=500, max_delay_ms=int(max_backoff_seconds * 1000)
        )
        if rate_limiter is not None:
            self._rate_limiter = rate_limiter
        else:
            from brokers.upstox.capabilities.snapshot import upstox_capabilities
            from infrastructure.resilience.rate_limiter import create_rate_limiter

            self._rate_limiter = create_rate_limiter("upstox", caps=upstox_capabilities())
        if session is not None:
            self._session = session
        else:
            self._session = requests.Session()
            from requests.adapters import HTTPAdapter

            adapter = HTTPAdapter(
                pool_connections=getattr(settings, "pool_connections", 50),
                pool_maxsize=getattr(settings, "pool_maxsize", 100),
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

        # Resilience patterns (RES-03, RES-04)
        # Note: Retry is handled at the adapter/context level via RetryExecutor,
        # not in the HTTP client itself. See brokers.upstox.auth.context.
        self._enable_circuit_breaker = enable_circuit_breaker

        if enable_circuit_breaker:
            default_cb = circuit_breaker or CircuitBreaker(
                name="upstox_api",
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=3,
                    open_duration_ms=30_000,
                ),
            )
            self._circuit_breaker = default_cb
            self._read_circuit_breaker = read_circuit_breaker or CircuitBreaker(
                name="upstox_api_read",
                config=CircuitBreakerConfig(
                    failure_threshold=10,
                    success_threshold=3,
                    open_duration_ms=15_000,
                ),
            )
            self._write_circuit_breaker = write_circuit_breaker or CircuitBreaker(
                name="upstox_api_write",
                config=CircuitBreakerConfig(
                    failure_threshold=3,
                    success_threshold=2,
                    open_duration_ms=30_000,
                ),
            )
            self._admin_circuit_breaker = admin_circuit_breaker or CircuitBreaker(
                name="upstox_api_admin",
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=3,
                    open_duration_ms=30_000,
                ),
            )
        else:
            self._circuit_breaker = None
            self._read_circuit_breaker = None
            self._write_circuit_breaker = None
            self._admin_circuit_breaker = None

        from brokers.common.http.resilient_transport import ResilientHttpTransport

        self._resilient_transport = ResilientHttpTransport(
            rate_limiter=_UpstoxRateLimitAdapter(self),
            circuit_breaker=None,
        )

    @property
    def settings(self) -> Any:
        """Expose the underlying settings (algo_name, rest_base_url, etc.)."""
        return self._settings

    @property
    def rate_limiter(self) -> MultiBucketRateLimiter:
        """Expose the rate limiter for observability metrics."""
        return self._rate_limiter

    def _get_circuit_breaker(self, url: str, method: str) -> CircuitBreaker | None:
        if not self._enable_circuit_breaker:
            return None
        category = _categorize_upstox_url(url, method)
        if category == "read":
            return self._read_circuit_breaker
        if category == "write":
            return self._write_circuit_breaker
        return self._admin_circuit_breaker

    def circuit_breaker_states(self) -> dict[str, int]:
        """Public observability surface — no private ``_read_circuit_breaker`` reaches."""
        from infrastructure.resilience.circuit_breaker import CircuitState

        mapping = {
            "read": self._read_circuit_breaker,
            "write": self._write_circuit_breaker,
            "admin": self._admin_circuit_breaker,
        }
        return {
            name: cb.state.value if cb is not None else CircuitState.CLOSED.value
            for name, cb in mapping.items()
        }

    def _headers(self, algo_name: str | None = None, *, url: str = "") -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token_provider()}",
        }
        if "/v3/" in url:
            headers["Api-Version"] = "3.0"
        algo = algo_name or getattr(self._settings, "algo_name", "")
        if algo:
            headers["X-Algo-Name"] = algo
        return headers

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(method="GET", url=url, params=params)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        algo_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            method="POST", url=url, json=payload, algo_name=algo_name, params=params
        )

    def put_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        algo_name: str | None = None,
    ) -> dict[str, Any]:
        return self._request(method="PUT", url=url, json=payload, algo_name=algo_name)

    def delete_json(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        algo_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            method="DELETE",
            url=url,
            json=payload,
            algo_name=algo_name,
            params=params,
        )

    def _request(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        algo_name: str | None = None,
    ) -> dict[str, Any]:
        # Circuit breaker: fail fast if circuit is open (category-specific)
        cb = self._get_circuit_breaker(url, method)
        if cb is not None:
            from infrastructure.resilience.circuit_breaker import CircuitState
            from infrastructure.resilience.errors import CircuitBreakerOpenError

            if cb.state == CircuitState.OPEN:
                logger.warning(
                    "Upstox API circuit breaker is open for %s %s",
                    method,
                    url,
                )
                raise CircuitBreakerOpenError(cb.name)

        try:
            result = self._execute_request(
                method=method,
                url=url,
                json=json,
                params=params,
                algo_name=algo_name,
            )
            if cb is not None:
                cb.on_success()
            return result
        except Exception:
            if cb is not None:
                cb.on_failure()
            raise

    def _execute_request(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        algo_name: str | None = None,
    ) -> dict[str, Any]:
        bucket = _rate_limit_bucket(url)
        last_auth_error: UpstoxAuthError | None = None
        last_exc: UpstoxApiError | None = None
        auth_refreshed = False

        if _is_ambiguous_write(method, url):
            total_attempts = 1
        else:
            # One slot for the token-refresh path plus `max_retries` transient slots.
            total_attempts = self._max_retries + 2

        for attempt in range(total_attempts):
            from brokers.common.http.resilient_transport import EndpointPolicy

            policy = EndpointPolicy(
                bucket=bucket,
                is_write=_categorize_upstox_url(url, method) == "write",
            )
            try:
                self._resilient_transport.before_request(policy)
            except RuntimeError as exc:
                raise UpstoxApiError(
                    f"Rate limiter acquire timed out after "
                    f"{self._rate_limit_timeout}s for bucket '{bucket}' (url={url})",
                    status_code=None,
                ) from exc

            try:
                resp = self._session.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    timeout=self._timeout_seconds,
                    headers=self._headers(algo_name=algo_name, url=url),
                )
            except requests.exceptions.RequestException as exc:
                # Transient network/transport failure — backoff and retry.
                last_exc = UpstoxApiError(
                    f"Upstox API {method} {url} request failed: {exc}",
                    status_code=None,
                )
                if attempt < total_attempts - 1:
                    logger.warning(
                        "Upstox HTTP transient error, retrying (%s %s): %s",
                        method,
                        url,
                        exc,
                    )
                    self._backoff(attempt)
                    continue
                raise last_exc from exc

            if resp.status_code >= 400:
                if resp.status_code in (401, 403):
                    last_auth_error = UpstoxAuthError(
                        f"Upstox API {method} {url} failed: HTTP {resp.status_code}",
                        resp.status_code,
                        resp.text,
                    )
                    if (
                        not auth_refreshed
                        and self._on_auth_failure is not None
                        and self._on_auth_failure()
                    ):
                        auth_refreshed = True
                        logger.info(
                            "Upstox HTTP retry after token refresh: %s %s",
                            method,
                            url,
                        )
                        continue
                    raise last_auth_error

                # Transient server-side failures: 429 (rate limited) or 5xx.
                is_transient = resp.status_code == 429 or resp.status_code >= 500
                if resp.status_code == 429:
                    try:
                        from infrastructure.auth.metrics import AuthMetrics

                        AuthMetrics.api_rate_limit("upstox")
                    except Exception:
                        pass
                if resp.status_code == 423:
                    raise UpstoxFundsMaintenanceError(
                        "Upstox funds service is down for maintenance (12:00 AM–5:30 AM IST)",
                        resp.status_code,
                        resp.text,
                    )

                if is_transient and attempt < total_attempts - 1:
                    retry_after = self._parse_retry_after(resp)
                    last_exc = UpstoxApiError(
                        f"Upstox API {method} {url} failed: HTTP {resp.status_code}",
                        resp.status_code,
                        resp.text,
                    )
                    logger.warning(
                        "Upstox HTTP %s, retrying (%s %s) retry_after=%s",
                        resp.status_code,
                        method,
                        url,
                        retry_after,
                    )
                    self._backoff(attempt, retry_after=retry_after)
                    continue

                raise UpstoxApiError(
                    f"Upstox API {method} {url} failed: HTTP {resp.status_code}",
                    resp.status_code,
                    resp.text,
                )

            body = resp.json() if resp.text else {}
            if isinstance(body, dict) and str(body.get("status", "")).lower() in {
                "failure",
                "error",
            }:
                errors = body.get("errors")
                if isinstance(errors, list) and errors:
                    first = errors[0] if isinstance(errors[0], dict) else {}
                    message = first.get("message") or first.get("error")
                else:
                    message = (
                        body.get("message") or body.get("remarks") or "Upstox API returned failure"
                    )
                raise UpstoxApiError(str(message), resp.status_code, body)
            return body

        if last_auth_error is not None:
            raise last_auth_error
        if last_exc is not None:
            raise last_exc
        raise UpstoxAuthError(f"Upstox API {method} {url} failed after transient retries")

    def _parse_retry_after(self, resp: Any) -> float | None:
        """Parse ``Retry-After`` header (seconds only); return None if absent/invalid."""
        retry_after = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
        if not retry_after:
            return None
        try:
            return float(retry_after)
        except (TypeError, ValueError):
            # ``Retry-After`` as HTTP-date falls back to exponential backoff.
            return None

    def _backoff(self, attempt: int, retry_after: float | None = None) -> None:
        """Sleep before retrying: honor ``Retry-After`` for 429, else backoff."""
        if retry_after is not None:
            delay = min(max(retry_after, 0.0), 30.0)
        else:
            delay = self._backoff_strategy.delay(attempt)
        if delay > 0:
            time.sleep(delay)
