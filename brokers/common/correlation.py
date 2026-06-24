"""Shim — import from :mod:`infrastructure.correlation` (architecture review)."""

from infrastructure.correlation import (
    generate_correlation_id,
    get_current_correlation_id,
    set_current_correlation_id,
    with_correlation,
)

__all__ = [
    "generate_correlation_id",
    "get_current_correlation_id",
    "set_current_correlation_id",
    "with_correlation",
]
