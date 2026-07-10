"""Application-layer observability helpers — no infrastructure imports.

stdlib logging + optional no-op tracing so ``application`` stays hexagonal.
Composition roots may wrap with real OTEL later.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

F = TypeVar("F", bound=Callable[..., object])


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def trace_operation(operation_name: str) -> Callable[[F], F]:
    """No-op span decorator (real tracing wired at composition root if needed)."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
