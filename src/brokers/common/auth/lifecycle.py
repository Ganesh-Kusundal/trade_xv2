"""Shared auth lifecycle protocol and 401-once policy helpers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TokenLifecyclePort(Protocol):
    """Broker token lifecycle — implement in dhan/upstox auth modules."""

    broker_id: str

    def describe(self) -> dict[str, Any]: ...

    def bootstrap(self) -> str: ...

    def refresh_on_401(self) -> str | None: ...


def should_attempt_refresh(already_refreshed: bool) -> bool:
    """401-once policy: at most one remint per probe cycle."""
    return not already_refreshed


def merge_auth_error_detail(status_code: int, body: str = "") -> str:
    """Normalize auth failure detail for probes and HTTP clients."""
    if status_code == 401:
        return "token rejected (401)"
    if status_code == 403:
        return "forbidden (403)"
    return body or f"HTTP {status_code}"
