"""Unit tests for the minimal FillReducer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.fill_reducer import FillEvent, FillReducer


def _fill(
    fill_id: str = "F1",
    order_id: str = "O1",
    quantity: int = 5,
    cumulative_quantity: int = 5,
    order_qty: int = 10,
) -> tuple[FillEvent, int]:
    return (
        FillEvent(
            fill_id=fill_id,
            order_id=order_id,
            quantity=quantity,
            cumulative_quantity=cumulative_quantity,
            price=Decimal("100"),
            fees=Decimal("1.50"),
        ),
        order_qty,
    )


class TestFillReducer:
    def test_valid_fill_is_accepted(self) -> None:
        reducer = FillReducer()
        fill, order_qty = _fill()

        result = reducer.apply(fill, order_quantity=order_qty, prior_cumulative=0)

        assert result.accepted is True
        assert result.reason == ""

    def test_duplicate_fill_id_is_rejected(self) -> None:
        reducer = FillReducer()
        fill, order_qty = _fill()

        assert reducer.apply(fill, order_quantity=order_qty).accepted is True
        duplicate = reducer.apply(fill, order_quantity=order_qty)

        assert duplicate.accepted is False
        assert "duplicate fill_id" in duplicate.reason

    def test_overfill_is_rejected(self) -> None:
        reducer = FillReducer()
        fill, _ = _fill(cumulative_quantity=15, order_qty=10)

        result = reducer.apply(fill, order_quantity=10)

        assert result.accepted is False
        assert "exceeds order quantity" in result.reason

    def test_cumulative_decrease_is_rejected(self) -> None:
        reducer = FillReducer()
        first, order_qty = _fill(fill_id="F1", cumulative_quantity=5)
        second, _ = _fill(fill_id="F2", cumulative_quantity=3)

        assert reducer.apply(first, order_quantity=order_qty, prior_cumulative=0).accepted is True
        result = reducer.apply(second, order_quantity=order_qty, prior_cumulative=5)

        assert result.accepted is False
        assert "decreased" in result.reason

    def test_fill_from_trade_builds_cumulative(self) -> None:
        event = FillReducer.fill_from_trade(
            "T1",
            "O1",
            quantity=3,
            prior_filled=2,
            price=Decimal("250"),
            fees=Decimal("0.75"),
        )

        assert event.cumulative_quantity == 5
        assert event.fees == Decimal("0.75")

    def test_fill_event_requires_fill_id(self) -> None:
        with pytest.raises(ValueError, match="fill_id"):
            FillEvent(
                fill_id="",
                order_id="O1",
                quantity=1,
                cumulative_quantity=1,
                price=Decimal("1"),
            )
