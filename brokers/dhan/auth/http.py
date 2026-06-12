"""Authenticated HTTP client for Dhan v2 REST endpoints.

Handles the ``access-token`` / ``client-id`` header injection common to all
Dhan REST calls and raises :class:`~broker.dhan.exceptions.DhanApiError` on
non-success responses so that the retry executor can catch and back off
appropriately.

Design reference: Trade_J ``DhanAuthenticatedHttpClient``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Union

import requests

from brokers.dhan.auth.auth import DhanTokenProvider
from brokers.dhan.exceptions import DhanApiError, DhanAuthenticationError

TokenSource = Union[Callable[[], str], DhanTokenProvider]


class DhanAuthenticatedHttpClient:
    """Small authenticated HTTP client for Dhan v2 REST endpoints."""

    def __init__(
        self,
        token_provider: TokenSource,
        settings: Any,
        *,
        timeout_seconds: int = 15,
        session: requests.Session | None = None,
    ) -> None:
        self._token_provider = token_provider
        self._settings = settings
        self._timeout_seconds = timeout_seconds
        if session is not None:
            self._session = session
        else:
            self._session = requests.Session()
            # Configure connection pooling to support high-concurrency requests
            from requests.adapters import HTTPAdapter

            pool_conn = getattr(settings, "pool_connections", 50)
            pool_max = getattr(settings, "pool_maxsize", 100)
            adapter = HTTPAdapter(pool_connections=pool_conn, pool_maxsize=pool_max)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    # ── Public verbs ─────────────────────────────────────────────────

    def get_json(self, url: str) -> dict[str, Any]:
        return self._request("GET", url)

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", url, payload)

    def put_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", url, payload)

    def delete_json(self, url: str) -> dict[str, Any]:
        return self._request("DELETE", url)

    # ── Internal ─────────────────────────────────────────────────────

    def _resolve_token(self) -> str:
        provider = self._token_provider
        if isinstance(provider, DhanTokenProvider):
            return provider.ensure_valid_and_get()
        return provider()

    def _token_generation_id(self) -> int:
        provider = self._token_provider
        if isinstance(provider, DhanTokenProvider):
            return provider.token_generation_id()
        return 0

    def _invalidate_token_generation(self, failed_generation_id: int) -> None:
        provider = self._token_provider
        if isinstance(provider, DhanTokenProvider):
            if not provider.invalidate_generation(failed_generation_id):
                provider.invalidate()

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: DhanApiError | None = None
        for attempt in range(2):
            generation_id = self._token_generation_id()
            token = self._resolve_token()
            resp = self._session.request(
                method,
                url,
                json=payload,
                timeout=self._timeout_seconds,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "access-token": token,
                    "client-id": self._settings.client_id,
                },
            )
            if resp.status_code >= 400:
                error = self._build_http_error(method, url, resp)
                if attempt == 0 and self._is_auth_failure(resp):
                    self._invalidate_token_generation(generation_id)
                    last_error = error
                    continue
                raise error
            body = resp.json() if resp.text else {}
            if isinstance(body, dict) and str(body.get("status", "")).lower() in {
                "failure",
                "error",
            }:
                message = body.get("remarks") or body.get("message") or "Dhan API returned failure"
                error = DhanApiError(str(message), resp.status_code, body)
                if attempt == 0 and self._is_auth_failure_body(body, resp.status_code):
                    self._invalidate_token_generation(generation_id)
                    last_error = error
                    continue
                raise error
            return body
        if last_error is not None:
            raise last_error
        raise DhanApiError(f"Dhan API {method} {url} failed after auth retry")

    @staticmethod
    def _build_http_error(method: str, url: str, resp: requests.Response) -> DhanApiError:
        if DhanAuthenticatedHttpClient._is_auth_failure(resp):
            return DhanAuthenticationError(
                f"Dhan API {method} {url} failed: HTTP {resp.status_code}",
                resp.status_code,
                resp.text,
            )
        return DhanApiError(
            f"Dhan API {method} {url} failed: HTTP {resp.status_code}",
            resp.status_code,
            resp.text,
        )

    @staticmethod
    def _is_auth_failure(resp: requests.Response) -> bool:
        if resp.status_code == 401:
            return True
        if resp.status_code != 400:
            return False
        return DhanAuthenticatedHttpClient._is_auth_failure_body(
            DhanAuthenticatedHttpClient._safe_json(resp.text),
            resp.status_code,
        )

    @staticmethod
    def _is_auth_failure_body(body: Any, status_code: int) -> bool:
        if status_code == 401:
            return True
        if status_code != 400:
            return False
        if not isinstance(body, dict):
            return False
        error_code = str(body.get("errorCode", ""))
        if error_code in {"DH-906", "DH-808"}:
            return True
        error_message = str(body.get("errorMessage", "")).lower()
        if "invalid token" in error_message:
            return True
        data = body.get("data")
        if isinstance(data, dict):
            for value in data.values():
                text = str(value).lower()
                if "authentication failed" in text or "invalid token" in text:
                    return True
                if str(value) in {"806", "808"}:
                    return True
        return False

    @staticmethod
    def _safe_json(text: str) -> Any:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
