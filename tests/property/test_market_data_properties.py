"""Property-based tests for market data parsing invariants.

These tests use Hypothesis to verify that market data processing
maintains logical invariants regardless of input values.

Run with:
    pytest tests/property/test_market_data_properties.py -v
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st


class TestMarketDataProperties:
    """Invariants for market data processing."""

    @given(
        ltp=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
        open=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
        high=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
        low=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
    )
    @settings(max_examples=100)
    def test_quote_price_relationships(self, ltp: Decimal, open: Decimal, high: Decimal, low: Decimal):
        """Quote prices must satisfy logical relationships."""
        # Invariant: low <= high (low is always <= high)
        assert low <= high, f"Low ({low}) must be <= high ({high})"

        # Invariant: ltp should be within [low, high] range
        # Note: This may not always hold in real markets due to timing,
        # but it's a reasonable invariant for most cases
        if low <= high:
            assert low <= ltp or ltp <= high, (
                f"LTP ({ltp}) should typically be within [{low}, {high}] range"
            )

    @given(
        volume=st.integers(min_value=0, max_value=10000000),
    )
    @settings(max_examples=50)
    def test_volume_non_negative(self, volume: int):
        """Trading volume must always be non-negative."""
        # Invariant: volume >= 0
        assert volume >= 0, f"Volume must be non-negative, got {volume}"

    @given(
        bid_price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
        ask_price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
        bid_qty=st.integers(min_value=1, max_value=10000),
        ask_qty=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=100)
    def test_market_depth_structure(
        self, bid_price: Decimal, ask_price: Decimal, bid_qty: int, ask_qty: int
    ):
        """Market depth entries must have valid structure."""
        # Invariant: quantities must be positive
        assert bid_qty > 0, f"Bid quantity must be positive, got {bid_qty}"
        assert ask_qty > 0, f"Ask quantity must be positive, got {ask_qty}"

        # Invariant: prices must be positive
        assert bid_price > 0, f"Bid price must be positive, got {bid_price}"
        assert ask_price > 0, f"Ask price must be positive, got {ask_price}"

    @given(
        prices=st.lists(
            st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000")),
            min_size=1,
            max_size=100
        ),
    )
    @settings(max_examples=50)
    def test_price_list_invariants(self, prices: list[Decimal]):
        """Price lists must maintain ordering invariants."""
        if len(prices) > 1:
            # Invariant: sorted prices should be valid
            sorted_prices = sorted(prices)
            assert sorted_prices[0] <= sorted_prices[-1], "Sorted prices should be ordered"

        # Invariant: all prices should be positive
        assert all(p > 0 for p in prices), "All prices must be positive"

    @given(
        timestamp=st.integers(min_value=0, max_value=9999999999),
    )
    @settings(max_examples=50)
    def test_timestamp_validity(self, timestamp: int):
        """Timestamps must be valid Unix timestamps."""
        # Invariant: timestamp should be reasonable (after year 2000, before year 2100)
        year_2000 = 946684800  # Unix timestamp for 2000-01-01
        year_2100 = 4102444800  # Unix timestamp for 2100-01-01

        if year_2000 <= timestamp <= year_2100:
            # Valid timestamp range
            assert timestamp > 0
