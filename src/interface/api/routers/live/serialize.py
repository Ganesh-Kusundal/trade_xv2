"""Serialize broker domain objects for live REST responses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any


def serialize_value(obj: Any) -> Any:
    """Convert domain types to JSON-safe structures."""
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return serialize_value(obj.to_dict())
    if is_dataclass(obj):
        return {k: serialize_value(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list | tuple):
        return [serialize_value(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): serialize_value(v) for k, v in obj.items()}
    return obj
