"""Tests for defensive quote normalization."""

from __future__ import annotations

from decimal import Decimal


from domain.value_objects import InstrumentId
from plugins.brokers.common.quote_normalize import normalize_quote


class TestDefensiveQuoteNormalization:
    """normalize_quote should handle missing keys gracefully."""

    def test_empty_dict_returns_zero_prices(self) -> None:
        """Empty quote dict should not crash, returns zero prices."""
        quote = normalize_quote({}, instrument_id=InstrumentId.parse("NSE:RELIANCE"))
        assert quote.bid.value == Decimal("0")
        assert quote.ask.value == Decimal("0")
        assert quote.bid_size.value == Decimal("0")
        assert quote.ask_size.value == Decimal("0")

    def test_partial_quote_fills_missing_with_defaults(self) -> None:
        """Partial quote should fill missing keys with defaults."""
        quote = normalize_quote(
            {"bid": "100.50"},
            instrument_id=InstrumentId.parse("NSE:TCS"),
        )
        assert quote.bid.value == Decimal("100.50")
        assert quote.ask.value == Decimal("0")  # default
        assert quote.bid_size.value == Decimal("0")  # default

    def test_invalid_values_fall_back_to_defaults(self) -> None:
        """Invalid values should fall back to defaults instead of crashing."""
        # Should not raise - invalid values get defaulted
        quote = normalize_quote(
            {"bid": "invalid", "ask": None, "bid_size": "", "ask_size": "NaN"},
            instrument_id=InstrumentId.parse("NSE:INFY"),
        )
        assert quote.instrument_id.value == "NSE:INFY"

    def test_complete_quote_parses_all_fields(self) -> None:
        """Complete quote should parse all fields correctly."""
        quote = normalize_quote(
            {"bid": "100.50", "ask": "101.00", "bid_size": "500", "ask_size": "300"},
            instrument_id=InstrumentId.parse("NSE:HDFC"),
        )
        assert quote.bid.value == Decimal("100.50")
        assert quote.ask.value == Decimal("101.00")
        assert quote.bid_size.value == Decimal("500")
        assert quote.ask_size.value == Decimal("300")

    def test_zero_values_are_preserved(self) -> None:
        """Zero values should be preserved, not replaced with defaults."""
        quote = normalize_quote(
            {"bid": "0", "ask": "0", "bid_size": "0", "ask_size": "0"},
            instrument_id=InstrumentId.parse("NSE:TEST"),
        )
        assert quote.bid.value == Decimal("0")
        assert quote.ask.value == Decimal("0")
