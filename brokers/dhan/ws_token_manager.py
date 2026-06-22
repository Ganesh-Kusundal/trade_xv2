"""DhanTokenManager — token refresh and validation.

Responsibility: Manage access token lifecycle including static token storage,
dynamic token retrieval via callable, token updates, and validation.
Thread-safe via RLock.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)


class DhanTokenManager:
    """Manages Dhan access token lifecycle.

    Supports both static token (stored string) and dynamic token
    (callable that returns fresh token). The callable takes precedence
    when both are provided.

    Thread-safe: All token access is protected by RLock.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> None:
        """Initialize token manager.

        Args:
            client_id: Dhan client ID.
            access_token: Static access token (fallback if fn not provided/fails).
            access_token_fn: Callable returning fresh token (preferred over static).
        """
        self._client_id = client_id
        self._access_token = access_token or ""
        self._access_token_fn = access_token_fn
        self._lock = threading.RLock()

    @property
    def client_id(self) -> str:
        """Return the client ID."""
        return self._client_id

    def get_token(self) -> str:
        """Get the current access token.

        If access_token_fn is provided, calls it and returns the result.
        If the callable raises, logs the error and falls back to the
        static token.

        Returns:
            Current access token string. Empty string if unavailable.
        """
        with self._lock:
            if self._access_token_fn is not None:
                try:
                    return self._access_token_fn()
                except Exception as exc:
                    logger.error(
                        "dhan_ws_access_token_fn_failed",
                        extra={
                            "exception_type": type(exc).__name__,
                            "exception_message": str(exc),
                        },
                    )
            return self._access_token

    def update_token(self, token: str) -> None:
        """Update the static token snapshot.

        This is called by external token refresh schedulers to push
        a new token. If a token_fn is also configured, it still takes
        precedence in get_token().

        Args:
            token: New access token string.
        """
        with self._lock:
            self._access_token = token

    def is_token_valid(self) -> bool:
        """Check if the current token is valid (non-empty).

        Returns:
            True if token is non-empty and non-whitespace.
        """
        with self._lock:
            if self._access_token_fn is not None:
                try:
                    token = self._access_token_fn()
                    return bool(token and token.strip())
                except Exception:
                    pass
            return bool(self._access_token and self._access_token.strip())
