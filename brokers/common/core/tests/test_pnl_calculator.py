"""Tests for PnLCalculator — pure function, deterministic, no side effects."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.common.core.domain import Position
from brokers.common.core.pnl_calculator import PnLCalculator, PnLSnapshot


class TestPnLSnapshot:
    """Test the immutable PnLSnapshot dataclass."""

    def test_defaults(self) -> None:
        s = PnLSnapshot()
        assert s.total_unrealized == Decimal("0")
        assert s.total_realized == Decimal("0")
        assert s.total_pnl == Decimal("0")
        assert s.position_count == 0
        assert s.long_count == 0
        assert s.short_count == 0
        assert s.flat_count == 0

    def test_is_profitable(self) -> None:
        s = PnLSnapshot(total_pnl=Decimal("100"))
        assert s.is_profitable is True
        assert s.is_loss is False

    def test_is_loss(self) -> None:
        s = PnLSnapshot(total_pnl=Decimal("-50"))
        assert s.is_profitable is False
        assert s.is_loss is True

    def test_zero_is_neither(self) -> None:
        s = PnLSnapshot(total_pnl=Decimal("0"))
        assert s.is_profitable is False
        assert s.is_loss is False

    def test_is_frozen(self) -> None:
        s = PnLSnapshot()
        with pytest.raises(Exception):  # frozen=True raises FrozenInstanceError or AttributeError
            s.total_pnl = Decimal("100")


class TestPnLCalculatorCompute:
    """Test the main compute() method."""

    def test_empty_positions(self) -> None:
        result = PnLCalculator.compute([])
        assert result.position_count == 0
        assert result.total_unrealized == Decimal("0")
        assert result.total_realized == Decimal("0")
        assert result.total_pnl == Decimal("0")

    def test_single_long_position_profit(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2600"),
        )
        result = PnLCalculator.compute([pos])
        assert result.position_count == 1
        assert result.long_count == 1
        assert result.short_count == 0
        assert result.flat_count == 0
        assert result.total_unrealized == Decimal("1000")  # 10 * (2600 - 2500)
        assert result.total_realized == Decimal("0")
        assert result.total_pnl == Decimal("1000")

    def test_single_short_position_profit(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=-10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2400"),
        )
        result = PnLCalculator.compute([pos])
        assert result.short_count == 1
        assert result.total_unrealized == Decimal("1000")  # 10 * (2500 - 2400)
        assert result.total_pnl == Decimal("1000")

    def test_mixed_positions(self) -> None:
        long_pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2600"),
            unrealized_pnl=Decimal("1000"),
            realized_pnl=Decimal("500"),
        )
        short_pos = Position(
            symbol="TCS",
            exchange="NSE",
            quantity=-5,
            avg_price=Decimal("3500"),
            ltp=Decimal("3600"),
            unrealized_pnl=Decimal("-500"),
            realized_pnl=Decimal("200"),
        )
        result = PnLCalculator.compute([long_pos, short_pos])
        assert result.position_count == 2
        assert result.long_count == 1
        assert result.short_count == 1
        assert result.total_unrealized == Decimal("500")  # 1000 + (-500)
        assert result.total_realized == Decimal("700")  # 500 + 200
        assert result.total_pnl == Decimal("1200")  # 500 + 700

    def test_flat_position(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=0,
            avg_price=Decimal("0"),
            ltp=Decimal("2500"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("100"),
        )
        result = PnLCalculator.compute([pos])
        assert result.flat_count == 1
        assert result.total_pnl == Decimal("100")


class TestPnLCalculatorSinglePosition:
    """Test single-position helper methods."""

    def test_compute_unrealized(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2600"),
        )
        assert PnLCalculator.compute_unrealized(pos) == Decimal("1000")

    def test_compute_realized(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2600"),
            realized_pnl=Decimal("500"),
        )
        assert PnLCalculator.compute_realized(pos) == Decimal("500")


class TestPnLCalculatorDailyPnL:
    """Test compute_daily_pnl() helper."""

    def test_daily_pnl_empty(self) -> None:
        assert PnLCalculator.compute_daily_pnl([]) == Decimal("0")

    def test_daily_pnl_single_position(self) -> None:
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2600"),
            unrealized_pnl=Decimal("1000"),
            realized_pnl=Decimal("500"),
        )
        assert PnLCalculator.compute_daily_pnl([pos]) == Decimal("1500")

    def test_daily_pnl_multiple_positions(self) -> None:
        positions = [
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                avg_price=Decimal("2500"),
                ltp=Decimal("2600"),
                unrealized_pnl=Decimal("1000"),
                realized_pnl=Decimal("0"),
            ),
            Position(
                symbol="TCS",
                exchange="NSE",
                quantity=-5,
                avg_price=Decimal("3500"),
                ltp=Decimal("3400"),
                unrealized_pnl=Decimal("500"),
                realized_pnl=Decimal("200"),
            ),
        ]
        assert PnLCalculator.compute_daily_pnl(positions) == Decimal("1700")


class TestPnLCalculatorDeterministic:
    """Test that PnLCalculator is truly deterministic (pure function)."""

    def test_same_input_same_output(self) -> None:
        positions = [
            Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                avg_price=Decimal("2500"),
                ltp=Decimal("2600"),
                unrealized_pnl=Decimal("1000"),
                realized_pnl=Decimal("500"),
            ),
        ]
        result1 = PnLCalculator.compute(positions)
        result2 = PnLCalculator.compute(positions)
        assert result1 == result2

    def test_no_side_effects(self) -> None:
        """Calling compute() should not mutate the input positions."""
        pos = Position(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=10,
            avg_price=Decimal("2500"),
            ltp=Decimal("2600"),
            unrealized_pnl=Decimal("1000"),
            realized_pnl=Decimal("500"),
        )
        positions = [pos]
        _ = PnLCalculator.compute(positions)
        # Verify position is unchanged
        assert pos.quantity == 10
        assert pos.avg_price == Decimal("2500")
        assert pos.unrealized_pnl == Decimal("1000")
        assert pos.realized_pnl == Decimal("500")


class TestPnLCalculatorNotInstantiable:
    """Test that PnLCalculator cannot be instantiated."""

    def test_init_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="not instantiable"):
            PnLCalculator()  # type: ignore[call-arg]
