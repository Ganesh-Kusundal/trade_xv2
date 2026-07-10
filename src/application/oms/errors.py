"""OMS application-layer errors."""

from __future__ import annotations

import time

from domain.exceptions import TradeXV2Error


class OrderBlockedError(TradeXV2Error):
    """Raised when an order operation is blocked by OMS / kill-switch enforcement.

    Attributes
    ----------
    operation : str
        The operation that was blocked (place_order, cancel_order, modify_order).
    reason : str
        Human-readable explanation of why the operation was blocked.
    timestamp : float
        Unix timestamp when the block occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation or "unknown"
        self.reason = reason or message
        self.timestamp = time.time()
