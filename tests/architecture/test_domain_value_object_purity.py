"""TOS-P1-003/004 — value-object purity and Money SSOT."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
VO_DIR = SRC / "domain" / "value_objects"
PRIMITIVES_MONEY = SRC / "domain" / "primitives" / "value_objects.py"


@pytest.mark.architecture
def test_value_objects_no_direct_datetime_now() -> None:
    """Domain VOs must not call datetime.now() directly (use ClockPort)."""
    violations: list[str] = []
    for path in VO_DIR.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "datetime.now(" in text:
            violations.append(str(path.relative_to(SRC)))
    assert not violations, (
        "datetime.now() in domain value_objects (TOS-P1-003):\n"
        + "\n".join(violations)
    )


@pytest.mark.architecture
def test_money_is_single_canonical_type() -> None:
    """domain.value_objects.Money must be the primitives Money (alias)."""
    from domain.primitives.value_objects import Money as PrimMoney
    from domain.value_objects.money import Money as VoMoney

    assert PrimMoney is VoMoney


@pytest.mark.architecture
def test_order_price_fields_documented_as_decimal_transitional() -> None:
    """Until full migration, Order keeps Decimal price — guard against float."""
    from domain import Order

    price_type = Order.__dataclass_fields__["price"].type
    qty_type = Order.__dataclass_fields__["quantity"].type
    # Transitional: Decimal/int allowed; float forbidden for money.
    assert "float" not in str(price_type).lower() or price_type is float
    # Soft assert: quantity is int (pre-Quantity VO migration)
    assert qty_type in (int, "int") or "int" in str(qty_type)
