"""TOS-P1-003/004 — value-object purity and Money SSOT."""

from __future__ import annotations

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
    assert not violations, "datetime.now() in domain value_objects (TOS-P1-003):\n" + "\n".join(
        violations
    )


@pytest.mark.architecture
def test_money_is_single_canonical_type() -> None:
    """domain.value_objects.Money must be the primitives Money (alias)."""
    from domain.primitives.value_objects import Money as PrimMoney
    from domain.value_objects.money import Money as VoMoney

    assert PrimMoney is VoMoney


@pytest.mark.architecture
def test_order_fields_are_money_and_quantity() -> None:
    """Order price/qty fields are Money/Quantity (TOS-P1-004 complete)."""
    from domain import Order
    from domain.primitives import Money, Quantity

    # Annotations may be strings under from __future__ import annotations
    price_t = Order.__dataclass_fields__["price"].type
    qty_t = Order.__dataclass_fields__["quantity"].type
    assert price_t is Money or price_t == "Money" or getattr(price_t, "__name__", "") == "Money"
    assert qty_t is Quantity or qty_t == "Quantity" or getattr(qty_t, "__name__", "") == "Quantity"
    o = Order(
        order_id="1",
        symbol="A",
        exchange="NSE",
        side=__import__("domain", fromlist=["Side"]).Side.BUY,
        order_type=__import__("domain", fromlist=["OrderType"]).OrderType.LIMIT,
        quantity=1,
        price=1,
    )
    assert isinstance(o.price, Money)
    assert isinstance(o.quantity, Quantity)
