"""HTTP transport Protocol + rate-limited HttpTransport."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from plugins.brokers.common.circuit_breaker import CircuitBreakerConfig, CircuitBreakerHttpClient
from plugins.brokers.common.constants import RATE_REDUCTION_FACTOR, USER_AGENT
from plugins.brokers.common.http_client import HttpClient
from plugins.brokers.common.metrics import BrokerMetrics, NoOpMetrics
from plugins.brokers.common.rate_limit import MultiBucketRateLimiter
from plugins.brokers.common.retry import RetryConfig, RetryableHttpClient
from shared.errors import AuthenticationError, BrokerError, NetworkError, RateLimitError


class RateLimitExceeded(RuntimeError, RateLimitError):
    """HTTP 429 or local bucket exhaustion."""


@runtime_checkable
class BaseTransport(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...

    def post(self, path: str, **kwargs: Any) -> Any: ...

    def put(self, path: str, **kwargs: Any) -> Any: ...

    def delete(self, path: str, **kwargs: Any) -> Any: ...


class UrllibClient:
    """stdlib HTTP client — no new dependency required for sync REST."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        headers = dict(kwargs.get("headers") or {})
        data = kwargs.get("json")
        body: bytes | None = None
        if data is not None:
            body = json.dumps(data).encode()
            headers.setdefault("Content-Type", "application/json")
        params = kwargs.get("params")
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode()
                payload: Any = json.loads(raw) if raw else {}
                return int(resp.status), payload
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode() if exc.fp else ""
            try:
                payload = json.loads(raw) if raw else {"error": str(exc)}
            except json.JSONDecodeError:
                payload = {"error": raw or str(exc)}
            return int(exc.code), payload


class RequestsClient:
    """Connection-pooled HTTP client using requests.Session.

    G14: Reuses TCP connections via session for better performance.
    Falls back to UrllibClient if requests is not installed.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        try:
            import requests
            self._session = requests.Session()
            self._timeout = timeout
            self._requests = requests
        except ImportError:
            # Fallback to urllib if requests not available
            self._session = None  # type: ignore
            self._fallback = UrllibClient(timeout)

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        if self._session is None:
            return self._fallback.request(method, url, **kwargs)
        headers = dict(kwargs.get("headers") or {})
        data = kwargs.get("json")
        params = kwargs.get("params")
        try:
            resp = self._session.request(
                method=method.upper(),
                url=url,
                json=data,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            try:
                payload: Any = resp.json() if resp.text else {}
            except (ValueError, json.JSONDecodeError):
                payload = {"error": resp.text or f"HTTP {resp.status_code}"}
            return resp.status_code, payload
        except self._requests.exceptions.HTTPError as exc:
            if exc.response is not None:
                try:
                    payload = exc.response.json()
                except (ValueError, json.JSONDecodeError):
                    payload = {"error": exc.response.text or str(exc)}
                return exc.response.status_code, payload
            return 500, {"error": str(exc)}
        except Exception as exc:
            return 500, {"error": str(exc)}


def default_bucket_for_path(path: str, method: str) -> str:
    lower = path.lower()
    if any(p in lower for p in ("/order", "/super", "/forever", "/exit")):
        return "orders"
    if any(p in lower for p in ("/historical", "/charts", "/candle")):
        return "historical"
    if any(p in lower for p in ("/quote", "/ltp", "/marketfeed", "/market-quote", "/depth")):
        return "quotes"
    return "admin" if method.upper() == "GET" else "orders"


# G13: Write-endpoint detection for retry safety
_WRITE_ENDPOINTS = frozenset({"/orders", "/sliceorder", "/killswitch", "/modify", "/cancel"})


def is_write_endpoint(path: str, method: str) -> bool:
    """Check if this is a write endpoint (POST/PUT/DELETE to order paths).

    Used by retry logic to avoid auto-retrying ambiguous writes on timeout.
    """
    if method.upper() not in ("POST", "PUT", "DELETE"):
        return False
    lower = path.lower()
    return any(ep in lower for ep in _WRITE_ENDPOINTS)


class HttpTransport:
    """Rate-limited sync HTTP with injectable client + bearer token provider.

    Token lifecycle (mirrors legacy src/brokers pattern):
    - ``token_provider`` is called on *every* request — it should be
      ``ensure_token`` (active probe) not ``current`` (passive getter).
    - ``on_auth_failure`` is invoked once on HTTP 401/403; when it returns
      True the request is retried with the refreshed token.
    """

    def __init__(
        self,
        *,
        base_url: str,
        limiter: MultiBucketRateLimiter,
        token_provider: Callable[[], str],
        client: HttpClient | None = None,
        bucket_for_path: Callable[[str, str], str] | None = None,
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer ",
        acquire_timeout: float = 5.0,
        extra_headers: dict[str, str] | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        retry_config: RetryConfig | None = None,
        on_auth_failure: Callable[[], bool] | None = None,
        metrics: BrokerMetrics | None = None,
        use_requests: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._limiter = limiter
        self._token_provider = token_provider
        # G14: Prefer RequestsClient (connection pooling) over UrllibClient
        if client is None:
            client = RequestsClient() if use_requests else UrllibClient()
        raw_client = client
        # Apply circuit breaker if configured
        if circuit_breaker_config:
            raw_client = CircuitBreakerHttpClient(raw_client, circuit_breaker_config)
        # Apply retry if configured
        if retry_config:
            raw_client = RetryableHttpClient(raw_client, retry_config)
        self._client = raw_client
        self._bucket_for_path = bucket_for_path or default_bucket_for_path
        self._auth_header = auth_header
        self._auth_prefix = auth_prefix
        self._acquire_timeout = acquire_timeout
        self._extra_headers = dict(extra_headers or {})
        self._on_auth_failure = on_auth_failure
        # G8: Metrics integration (no-op by default)
        self._metrics = metrics or NoOpMetrics()

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._request("DELETE", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        import time
        start = time.monotonic()
        bucket = self._bucket_for_path(path, method)
        if not self._limiter.acquire(bucket, timeout=self._acquire_timeout):
            self._metrics.record_rate_limit(bucket)
            raise RateLimitExceeded(f"local rate limit timeout: {bucket}")
        headers = dict(self._extra_headers)
        headers.setdefault("User-Agent", USER_AGENT)
        headers.update(kwargs.pop("headers", {}) or {})
        token = self._token_provider()
        if token:
            headers[self._auth_header] = f"{self._auth_prefix}{token}"
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        # G13: Pass is_write flag to retry client for write-safety
        is_write = is_write_endpoint(path, method)
        status, body = self._client.request(method, url, headers=headers, is_write=is_write, **kwargs)
        # Record metrics for the request
        duration_ms = (time.monotonic() - start) * 1000.0
        self._metrics.record_request(bucket, duration_ms, status)
        if status == 429:
            self._metrics.record_rate_limit(bucket)
            self._limiter.trigger_cooldown(bucket)
            raise RateLimitExceeded(f"HTTP 429 on {path}")
        # 401/403 → try re-auth once, then retry (mirrors legacy on_auth_failure)
        if status in (401, 403) and self._on_auth_failure is not None:
            if self._on_auth_failure():
                self._metrics.record_auth_refresh()
                # Re-fetch token (ensure_token just refreshed it)
                new_token = self._token_provider()
                if new_token:
                    headers[self._auth_header] = f"{self._auth_prefix}{new_token}"
                status, body = self._client.request(method, url, headers=headers, is_write=is_write, **kwargs)
                if status not in (401, 403):
                    # Retry succeeded — fall through to normal status handling
                    pass
                else:
                    raise AuthenticationError(f"HTTP {status} on {path}: {body}")
            else:
                raise AuthenticationError(f"HTTP {status} on {path}: {body}")
        if status in (401, 403):
            raise AuthenticationError(f"HTTP {status} on {path}: {body}")
        if status >= 500:
            raise NetworkError(f"HTTP {status} on {path}: {body}")
        if status >= 400:
            raise BrokerError(f"HTTP {status} on {path}: {body}")
        return body
