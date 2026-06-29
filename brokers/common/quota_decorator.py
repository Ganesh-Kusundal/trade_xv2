"""Quota-aware routing decorator for IntelligentMarketDataGateway.

Extracts the repeated pattern:
    gateway = self._get_gateway(operation)
    broker_id = getattr(gateway, "broker_id", self._primary)
    token = self._acquire_quota(broker_id, endpoint_class)
    try:
        return gateway.method(*args, **kwargs)
    finally:
        self._release_quota(token)

Usage:
    @routed(OperationKind.GET_QUOTE, "quotes")
    def ltp(self, symbol, exchange="NSE"):
        return self._gateway.ltp(symbol, exchange)
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def routed(operation: Any, endpoint_class: str) -> Callable:
    """Decorator that adds routing and quota management to gateway methods.

    The decorated method should accept `self` and call `self._gateway`
    (set by the decorator) to access the routed gateway instance.

    Args:
        operation: OperationKind enum value for routing.
        endpoint_class: Quota endpoint class string (e.g., "quotes", "historical").
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            # Get routed gateway
            gateway = self._get_gateway(operation)
            broker_id = getattr(gateway, "broker_id", self._primary)

            # Acquire quota token
            token = self._acquire_quota(broker_id, endpoint_class)

            # Set gateway reference for the wrapped method
            self._gateway = gateway

            try:
                return fn(self, *args, **kwargs)
            finally:
                self._release_quota(token)

        return wrapper

    return decorator
