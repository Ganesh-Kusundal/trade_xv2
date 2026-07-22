"""HTTP transport Protocol + rate-limited HttpTransport."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from plugins.brokers.common.rate_limit import MultiBucketRateLimiter


class RateLimitExceeded(RuntimeError):
    """HTTP 429 or local bucket exhaustion."""


@runtime_checkable
class BaseTransport(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...

    def post(self, path: str, **kwargs: Any) -> Any: ...

    def put(self, path: str, **kwargs: Any) -> Any: ...

    def delete(self, path: str, **kwargs: Any) -> Any: ...


@runtime_checkable
class HttpClient(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]: ...


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


def default_bucket_for_path(path: str, method: str) -> str:
    lower = path.lower()
    if any(p in lower for p in ("/order", "/super", "/forever", "/exit")):
        return "orders"
    if any(p in lower for p in ("/historical", "/charts", "/candle")):
        return "historical"
    if any(p in lower for p in ("/quote", "/ltp", "/marketfeed", "/market-quote", "/depth")):
        return "quotes"
    return "admin" if method.upper() == "GET" else "orders"


class HttpTransport:
    """Rate-limited sync HTTP with injectable client + bearer token provider."""

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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._limiter = limiter
        self._token_provider = token_provider
        self._client = client or UrllibClient()
        self._bucket_for_path = bucket_for_path or default_bucket_for_path
        self._auth_header = auth_header
        self._auth_prefix = auth_prefix
        self._acquire_timeout = acquire_timeout
        self._extra_headers = dict(extra_headers or {})

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._request("DELETE", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        bucket = self._bucket_for_path(path, method)
        if not self._limiter.acquire(bucket, timeout=self._acquire_timeout):
            raise RateLimitExceeded(f"local rate limit timeout: {bucket}")
        headers = dict(self._extra_headers)
        headers.setdefault(
            "User-Agent",
            "TradeXV2/0.1 (+https://github.com/tradex; python-urllib)",
        )
        headers.update(kwargs.pop("headers", {}) or {})
        token = self._token_provider()
        if token:
            headers[self._auth_header] = f"{self._auth_prefix}{token}"
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        status, body = self._client.request(method, url, headers=headers, **kwargs)
        if status == 429:
            self._limiter.reduce_rate(bucket, 0.5)
            raise RateLimitExceeded(f"HTTP 429 on {path}")
        if status >= 400:
            raise RuntimeError(f"HTTP {status} on {path}: {body}")
        return body
