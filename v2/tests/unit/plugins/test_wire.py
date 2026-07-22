"""BaseWireAdapter helpers — decimal, datetime, enum_value."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from domain.enums import OrderSide
from plugins.brokers.common.wire import BaseWireAdapter


class _Color(Enum):
    RED = "red"


def test_to_decimal_from_str_int_float() -> None:
    assert BaseWireAdapter.to_decimal("12.50") == Decimal("12.50")
    assert BaseWireAdapter.to_decimal(7) == Decimal("7")
    assert BaseWireAdapter.to_decimal(Decimal("1.5")) == Decimal("1.5")


def test_to_datetime_from_iso_and_datetime() -> None:
    raw = "2024-01-15T10:30:00+00:00"
    dt = BaseWireAdapter.to_datetime(raw)
    assert isinstance(dt, datetime)
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.tzinfo is not None

    already = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
    assert BaseWireAdapter.to_datetime(already) is already


def test_enum_value() -> None:
    assert BaseWireAdapter.enum_value(OrderSide.BUY) == "BUY"
    assert BaseWireAdapter.enum_value(_Color.RED) == "red"
    assert BaseWireAdapter.enum_value("plain") == "plain"
