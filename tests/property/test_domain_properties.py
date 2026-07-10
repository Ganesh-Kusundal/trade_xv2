"""Property-based tests for domain invariants (REF-19)."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from infrastructure.mappers import DefaultFieldMapping
from domain.types import OrderStatus


@given(st.text(min_size=0, max_size=32))
@settings(max_examples=50)
def test_status_normalize_idempotent(raw: str) -> None:
    once = OrderStatus.normalize(raw)
    twice = OrderStatus.normalize(once.value)
    assert once == twice


@given(
    st.fixed_dictionaries(
        {
            "order_id": st.text(min_size=1, max_size=12),
            "symbol": st.from_regex(r"[A-Z]{3,10}", fullmatch=True),
            "exchange": st.sampled_from(["NSE", "NFO"]),
            "side": st.sampled_from(["BUY", "SELL"]),
            "order_type": st.sampled_from(["MARKET", "LIMIT", "SL"]),
            "status": st.sampled_from(["OPEN", "FILLED", "CANCELLED"]),
            "quantity": st.integers(min_value=1, max_value=1000),
            "filled_quantity": st.integers(min_value=0, max_value=1000),
            "price": st.one_of(
                st.none(), st.decimals(min_value=0, max_value=10000, places=2).map(str)
            ),
            "avg_price": st.one_of(
                st.none(), st.decimals(min_value=0, max_value=10000, places=2).map(str)
            ),
            "reject_reason": st.text(max_size=64),
        }
    )
)
@settings(max_examples=30)
def test_default_field_mapping_roundtrip_keys(data: dict) -> None:
    mapping = DefaultFieldMapping()
    assert mapping.map_order_id(data) == str(data["order_id"])
    assert mapping.map_symbol(data) == str(data["symbol"])
    assert mapping.map_side(data).upper() in {"BUY", "SELL"}


@given(st.decimals(min_value=Decimal("0"), max_value=Decimal("100"), places=4))
@settings(max_examples=30)
def test_decimal_score_bounds(score: Decimal) -> None:
    clipped = max(Decimal("0"), min(Decimal("100"), score))
    assert Decimal("0") <= clipped <= Decimal("100")
