"""Broker error types — re-exported from domain for backward compatibility.

The canonical error hierarchy lives in ``domain.errors``. This module
(``infrastructure.resilience.errors``) re-exports every class so that existing
``from infrastructure.resilience.errors import BrokerError`` (and the
backward-compat facade ``tradex.runtime.resilience.errors``) continue to work
without modification. The ``convert_network_errors`` decorator
(infrastructure-level, depends on ``requests``) remains here since it is
broker-specific infrastructure.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

# ── Canonical re-exports from domain (reversed import direction) ──────
from domain.exceptions import (  # noqa: F401 — re-exports
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    CapabilityError,
    CircuitBreakerOpenError,
    ExitAllError,
    InstrumentError,
    InstrumentNotFoundError,
    MappingError,
    NetworkError,
    NonRetryableError,
    NotSupportedError,
    OrderError,
    RateLimitError,
    RejectedOrderError,
    RetryableError,
    TradeXV2RecoverableError,
)
from domain.exceptions import ConfigError as ConfigError
from domain.exceptions import DataError as DataError
from domain.exceptions import TradeXV2Error as TradeXV2Error
from domain.exceptions import ValidationError as ValidationError

F = TypeVar("F", bound=Callable[..., Any])


def convert_network_errors(
    error_factory: Callable[[Exception], NetworkError] | None = None,
) -> Callable[[F], F]:
    """Decorator that converts ``requests.RequestException`` → ``NetworkError``.

    Provides a standard infrastructure-level pattern for broker adapters:
    wrap the raw HTTP call so that callers only see domain exceptions,
    never transport-level ``requests`` exceptions.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except ImportError:
                raise
            except Exception as exc:
                try:
                    import requests as _requests
                except ImportError:
                    raise
                if isinstance(exc, _requests.RequestException):
                    if error_factory is not None:
                        raise error_factory(exc) from exc
                    raise NetworkError(str(exc)) from exc
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
