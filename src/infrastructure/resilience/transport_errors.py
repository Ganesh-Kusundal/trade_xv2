"""Map raw transport exceptions to canonical broker errors.

Lives in infrastructure so gateway code can use it without reaching into
brokers.common (keeps the infrastructure-independence import contract). The
brokers.common.transport_errors module re-exports these for backwards
compatibility with broker/runtime importers.
"""

from __future__ import annotations

from typing import Any

from domain.exceptions import (
    AuthenticationError,
    BrokerError,
    InstrumentNotFoundError,
    MappingError,
    NetworkError,
    OrderError,
    RateLimitError,
    RejectedOrderError,
)


def map_transport_exception(exc: BaseException) -> BrokerError:
    """Classify a transport-boundary exception into a canonical BrokerError."""
    if isinstance(exc, BrokerError):
        return exc
    name = type(exc).__name__
    msg = str(exc) or name
    lower = msg.lower()
    if "401" in lower or "auth" in lower or "token" in lower:
        return AuthenticationError(msg)
    if "429" in lower or "rate limit" in lower or "throttl" in lower:
        return RateLimitError(msg)
    if "mapping" in lower or "instrument key" in lower:
        return MappingError(msg)
    if "not found" in lower and "instrument" in lower:
        return InstrumentNotFoundError(msg)
    if "reject" in lower or "validation" in lower:
        return RejectedOrderError(msg)
    try:
        import requests

        if isinstance(exc, requests.RequestException):
            return NetworkError(msg)
    except ImportError:
        pass
    return OrderError(msg)


def order_result_from_transport_error(exc: BaseException):
    """Return OrderResult.fail with canonical error type prefix."""
    from domain.ports.protocols import OrderResult

    mapped = map_transport_exception(exc)
    return OrderResult.fail(f"{type(mapped).__name__}: {mapped}")


def order_result_from_response(response: Any):
    """Map a broker order mutation response to :class:`OrderResult`.

    Defaults to failure when ``success`` is absent — malformed responses must
    not silently become ``OrderResult.ok``.
    """
    from domain import OrderResponse
    from domain.ports.protocols import OrderResult

    if response is None:
        return OrderResult.fail("malformed broker response (None)")

    if isinstance(response, OrderResponse):
        if response.success:
            return OrderResult.ok(response)
        msg = response.message or response.error_code or "broker rejected order"
        return OrderResult.fail(msg)

    if isinstance(response, dict):
        if "success" not in response:
            return OrderResult.fail("malformed broker response (missing success)")
        if response.get("success"):
            return OrderResult.ok(response)
        msg = (
            response.get("message")
            or response.get("error")
            or response.get("errorMessage")
            or "broker rejected order"
        )
        return OrderResult.fail(str(msg))

    if not hasattr(response, "success"):
        return OrderResult.fail("malformed broker response (missing success)")

    if bool(response.success):
        return OrderResult.ok(response)

    msg = (
        getattr(response, "message", None)
        or getattr(response, "error", None)
        or "broker rejected order"
    )
    return OrderResult.fail(str(msg))


def order_response_from_transport_error(exc: BaseException):
    """Return OrderResponse.fail with canonical error type prefix."""
    from domain import OrderResponse

    mapped = map_transport_exception(exc)
    return OrderResponse.fail(f"{type(mapped).__name__}: {mapped}")


__all__ = [
    "map_transport_exception",
    "order_response_from_transport_error",
    "order_result_from_response",
    "order_result_from_transport_error",
]
