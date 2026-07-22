"""Wire helpers — normalize broker-native scalars to domain-safe types."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class BaseWireAdapter:
    @staticmethod
    def to_decimal(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def to_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        # ISO-8601; fromisoformat handles offset suffixes
        return datetime.fromisoformat(str(value))

    @staticmethod
    def enum_value(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        return value
