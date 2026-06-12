"""Authenticated HTTP client for Upstox REST endpoints.

Mirrors Trade_J ``UpstoxHttpClient``: Bearer + optional ``X-Algo-Name`` header
injection. Stateless w.r.t. the algo name — supplied per call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests

from .exceptions import UpstoxApiError, UpstoxAuthError


class UpstoxHttpClient:
    """Small authenticated HTTP client for Upstox v2 / v3 / HFT endpoints."""

    def __init__(
        self,
        token_provider: Callable[[], str],
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
            from requests.adapters import HTTPAdapter

            adapter = HTTPAdapter(
                pool_connections=getattr(settings, "pool_connections", 50),
                pool_maxsize=getattr(settings, "pool_maxsize", 100),
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    @property
    def settings(self) -> Any:
        """Expose the underlying settings (algo_name, rest_base_url, etc.)."""
        return self._settings

    def _headers(self, algo_name: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token_provider()}",
        }
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
        resp = self._session.request(
            method=method,
            url=url,
            json=json,
            params=params,
            timeout=self._timeout_seconds,
            headers=self._headers(algo_name=algo_name),
        )
        if resp.status_code >= 400:
            if resp.status_code in (401, 403):
                raise UpstoxAuthError(
                    f"Upstox API {method} {url} failed: HTTP {resp.status_code}",
                    resp.status_code,
                    resp.text,
                )
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
