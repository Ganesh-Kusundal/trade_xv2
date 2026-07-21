"""Shared utility helpers for broker modules."""

from __future__ import annotations

from typing import Any


def enum_value(value: Any) -> Any:
    """Extract the `.value` from an enum, or return the value as-is.

    Used when passing domain enums (Side, OrderType, etc.) to broker APIs
    that expect plain strings.
    """
    return value.value if hasattr(value, "value") else value
