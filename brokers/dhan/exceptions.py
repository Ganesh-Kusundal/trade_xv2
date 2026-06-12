"""Dhan-specific exception hierarchy.

All errors raised by the Dhan adapter layer surface through these types so
callers can differentiate API failures (retryable) from validation errors
(not retryable) without inspecting raw error strings.
"""

from __future__ import annotations

from typing import Any


class DhanApiError(RuntimeError):
    """Raised when a Dhan API response is not successful.

    Attributes:
        message: Human-readable description of the failure.
        status_code: HTTP status code (if the error was transport-level).
        payload: Raw response body (**not** for programmatic consumption;
            use ``DhanApiClient`` response helpers instead).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self.args[0]!r}, status_code={self.status_code!r})"
        )


class DhanAuthenticationError(DhanApiError):
    """Raised when Dhan rejects the access token (HTTP 401 / DH-906 / 808)."""
