"""Shared HTTP client protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HttpClient(Protocol):
    """Protocol for HTTP client implementations."""

    def request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]: ...
