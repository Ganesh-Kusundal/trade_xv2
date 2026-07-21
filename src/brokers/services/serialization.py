"""JSON-safe serialization helpers for broker domain objects.

Extracted from ``brokers.services.core`` to avoid the catch-all facade
importing serialisation utilities through the service entry point.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def safe_serialize(obj: object, *, _depth: int = 0, max_depth: int = 10) -> object:
    """Best-effort JSON-safe view of a domain object.

    *max_depth* caps recursion to prevent stack overflow on circular references.
    Objects beyond the limit are replaced with their type name.
    """
    if _depth > max_depth:
        return f"<{type(obj).__name__}>"
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    snap = getattr(obj, "snapshot", None)
    if callable(snap):
        return safe_serialize(snap(), _depth=_depth + 1, max_depth=max_depth)
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return safe_serialize(to_dict(), _depth=_depth + 1, max_depth=max_depth)
    if is_dataclass(obj):
        return {
            k: safe_serialize(v, _depth=_depth + 1, max_depth=max_depth)
            for k, v in asdict(obj).items()
        }
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {
            k: safe_serialize(v, _depth=_depth + 1, max_depth=max_depth)
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }
    if isinstance(obj, list | tuple):
        return [safe_serialize(v, _depth=_depth + 1, max_depth=max_depth) for v in obj]
    if isinstance(obj, dict):
        return {
            k: safe_serialize(v, _depth=_depth + 1, max_depth=max_depth) for k, v in obj.items()
        }
    return obj


__all__ = ["safe_serialize"]
