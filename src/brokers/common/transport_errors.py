"""Map raw transport exceptions to canonical broker errors."""

from __future__ import annotations

from domain.errors import (
    AuthenticationError,
    BrokerError,
    CapabilityError,
    InstrumentError,
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


def order_response_from_transport_error(exc: BaseException):
    """Return OrderResponse.fail with canonical error type prefix."""
    from domain import OrderResponse

    mapped = map_transport_exception(exc)
    return OrderResponse.fail(f"{type(mapped).__name__}: {mapped}")
