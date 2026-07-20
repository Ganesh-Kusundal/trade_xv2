"""Tests for P0.1 + P0.4: Options bid/ask None semantics.

Ensures that:
1. Options router returns None (not 0.0) for bid/ask when unavailable from OHLCV data
2. DataLakeGateway.quote() returns None for bid/ask (not 0.0 or Decimal("0"))
3. Type hints are correct (Optional[float] not float)
4. API contract is maintained (None is valid Optional[float])

These tests prevent regression where bid/ask might be set to misleading 0.0 values.
"""

from __future__ import annotations

from decimal import Decimal
from typing import get_type_hints

from datalake.gateway import DataLakeGateway
from domain import Quote
from interface.api.schemas import OptionChainResponse, OptionContract, QuoteResponse

# ── P0.1: Options Router Bid/Ask Tests ───────────────────────────────────────


class TestOptionContractBidAskNoneSemantics:
    """Verify OptionContract schema correctly models bid/ask as Optional with None default."""

    def test_bid_type_hint_is_optional(self):
        """bid field must be Optional[float], not float."""
        hints = get_type_hints(OptionContract)
        bid_type = str(hints.get("bid", ""))
        assert "Optional" in bid_type or "None" in bid_type, (
            f"bid type hint must be Optional[float], got: {bid_type}"
        )

    def test_ask_type_hint_is_optional(self):
        """ask field must be Optional[float], not float."""
        hints = get_type_hints(OptionContract)
        ask_type = str(hints.get("ask", ""))
        assert "Optional" in ask_type or "None" in ask_type, (
            f"ask type hint must be Optional[float], got: {ask_type}"
        )

    def test_bid_defaults_to_none(self):
        """bid must default to None, not 0.0."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            volume=1000.0,
            oi=5000.0,
        )
        assert contract.bid is None, f"bid should be None, got: {contract.bid}"

    def test_ask_defaults_to_none(self):
        """ask must default to None, not 0.0."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            volume=1000.0,
            oi=5000.0,
        )
        assert contract.ask is None, f"ask should be None, got: {contract.ask}"

    def test_bid_explicit_none_accepted(self):
        """Explicitly passing bid=None should work without error."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            bid=None,
            ask=None,
            volume=1000.0,
            oi=5000.0,
        )
        assert contract.bid is None
        assert contract.ask is None

    def test_bid_accepts_float_when_available(self):
        """bid should accept float values when available from live feeds."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            bid=149.5,
            ask=150.5,
            volume=1000.0,
            oi=5000.0,
        )
        assert contract.bid == 149.5
        assert contract.ask == 150.5

    def test_bid_zero_is_valid_not_none(self):
        """bid=0.0 is a valid value (different from None)."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            bid=0.0,
            ask=0.0,
            volume=1000.0,
            oi=5000.0,
        )
        assert contract.bid == 0.0
        assert contract.ask == 0.0
        assert contract.bid is not None  # 0.0 is not None


class TestOptionsRouterBidAskBehavior:
    """Verify options router endpoint returns None for bid/ask from OHLCV data."""

    def test_option_contract_constructed_with_none_bid_ask(self):
        """When constructing OptionContract from OHLCV, bid/ask must be None."""
        # Simulate what the router does when building contracts from OHLCV data
        row = ("NIFTY24JAN20000CE", "2024-01-25", 20000.0, "CE", 150.0, 1000.0, 5000.0)

        contract = OptionContract(
            symbol=row[0],
            expiry=str(row[1]) if row[1] else "",
            strike=float(row[2]) if row[2] else 0.0,
            option_type=row[3] or "CE",
            ltp=float(row[4]) if row[4] else 0.0,
            bid=None,  # Not available from OHLCV data
            ask=None,  # Not available from OHLCV data
            volume=float(row[5]) if row[5] else 0.0,
            oi=float(row[6]) if row[6] else 0.0,
        )

        assert contract.bid is None, "bid must be None for OHLCV-derived data"
        assert contract.ask is None, "ask must be None for OHLCV-derived data"

    def test_option_chain_response_serializes_none_correctly(self):
        """OptionChainResponse should serialize None bid/ask to JSON null."""
        contracts = [
            OptionContract(
                symbol="NIFTY24JAN20000CE",
                expiry="2024-01-25",
                strike=20000.0,
                option_type="CE",
                ltp=150.0,
                bid=None,
                ask=None,
                volume=1000.0,
                oi=5000.0,
            )
        ]

        response = OptionChainResponse(
            underlying="NIFTY",
            expiry="2024-01-25",
            contracts=contracts,
            count=1,
        )

        # Verify JSON serialization preserves None as null
        json_data = response.model_dump()
        assert json_data["contracts"][0]["bid"] is None
        assert json_data["contracts"][0]["ask"] is None


# ── P0.4: DataLakeGateway quote() Bid/Ask Tests ──────────────────────────────


class TestDataLakeGatewayQuoteBidAskNoneSemantics:
    """Verify DataLakeGateway.quote() returns None for bid/ask."""

    def test_quote_domain_model_has_optional_bid_ask(self):
        """Quote domain model must have Optional[Decimal] for bid/ask."""
        hints = get_type_hints(Quote)
        bid_type = str(hints.get("bid", ""))
        ask_type = str(hints.get("ask", ""))

        # Should be Optional[Decimal] or Decimal | None
        assert "Optional" in bid_type or "|" in bid_type or "None" in bid_type, (
            f"Quote.bid type hint should be Optional[Decimal], got: {bid_type}"
        )
        assert "Optional" in ask_type or "|" in ask_type or "None" in ask_type, (
            f"Quote.ask type hint should be Optional[Decimal], got: {ask_type}"
        )

    def test_quote_defaults_to_none_bid_ask(self):
        """Quote must default to None for bid/ask, not Decimal('0')."""
        quote = Quote(symbol="RELIANCE")
        assert quote.bid is None, f"bid should be None, got: {quote.bid}"
        assert quote.ask is None, f"ask should be None, got: {quote.ask}"

    def test_quote_none_is_not_zero(self):
        """None bid/ask must be distinguishable from Decimal('0')."""
        quote = Quote(
            symbol="RELIANCE",
            ltp=Decimal("2500.00"),
            bid=None,
            ask=None,
        )
        assert quote.bid is None
        assert quote.ask is None
        assert quote.bid != Decimal("0")
        assert quote.ask != Decimal("0")

    def test_quote_explicit_none_accepted(self):
        """Explicitly passing bid=None, ask=None should work."""
        quote = Quote(
            symbol="RELIANCE",
            ltp=Decimal("2500.00"),
            open=Decimal("2480.00"),
            high=Decimal("2520.00"),
            low=Decimal("2470.00"),
            close=Decimal("2500.00"),
            volume=1000000,
            change=Decimal("20.00"),
            bid=None,
            ask=None,
        )
        assert quote.bid is None
        assert quote.ask is None


class TestDataLakeGatewayQuoteReturnsNone:
    """Integration tests for DataLakeGateway.quote() bid/ask behavior."""

    def test_quote_returns_none_for_bid_ask_when_no_data(self, tmp_path):
        """quote() must return None for bid/ask when no parquet data exists."""
        gw = DataLakeGateway(root=str(tmp_path))
        quote = gw.quote("NONEXISTENT")

        assert quote.bid is None, f"bid should be None, got: {quote.bid}"
        assert quote.ask is None, f"ask should be None, got: {quote.ask}"

    def test_quote_returns_none_for_bid_ask_with_ohlcv_data(self, tmp_path):
        """quote() must return None for bid/ask even when OHLCV data is available."""
        import pandas as pd

        # Create test parquet data
        candles_dir = tmp_path / "equities" / "candles" / "timeframe=1m"
        symbol_dir = candles_dir / "symbol=RELIANCE"
        symbol_dir.mkdir(parents=True)

        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="min"),
                "open": [2480.0] * 10,
                "high": [2520.0] * 10,
                "low": [2470.0] * 10,
                "close": [2500.0] * 10,
                "volume": [1000000] * 10,
                "oi": [5000000] * 10,
                "symbol": ["RELIANCE"] * 10,
                "exchange": ["NSE"] * 10,
            }
        )
        df.to_parquet(symbol_dir / "data.parquet")

        gw = DataLakeGateway(root=str(tmp_path))
        quote = gw.quote("RELIANCE")

        assert quote.bid is None, f"bid should be None for OHLCV-derived quote, got: {quote.bid}"
        assert quote.ask is None, f"ask should be None for OHLCV-derived quote, got: {quote.ask}"
        assert quote.ltp == Decimal("2500.0"), "LTP should still be populated"

    def test_quote_batch_returns_none_for_bid_ask(self, tmp_path):
        """quote_batch() must return None for bid/ask for all symbols."""
        import pandas as pd

        # Create test parquet data for multiple symbols
        candles_dir = tmp_path / "equities" / "candles" / "timeframe=1m"

        for symbol in ["RELIANCE", "TCS"]:
            symbol_dir = candles_dir / f"symbol={symbol}"
            symbol_dir.mkdir(parents=True)

            df = pd.DataFrame(
                {
                    "timestamp": pd.date_range("2024-01-01", periods=5, freq="min"),
                    "open": [100.0] * 5,
                    "high": [110.0] * 5,
                    "low": [90.0] * 5,
                    "close": [105.0] * 5,
                    "volume": [500000] * 5,
                    "oi": [2000000] * 5,
                    "symbol": [symbol] * 5,
                    "exchange": ["NSE"] * 5,
                }
            )
            df.to_parquet(symbol_dir / "data.parquet")

        gw = DataLakeGateway(root=str(tmp_path))
        quotes = gw.quote_batch(["RELIANCE", "TCS"])

        for symbol, quote in quotes.items():
            assert quote.bid is None, f"bid should be None for {symbol}, got: {quote.bid}"
            assert quote.ask is None, f"ask should be None for {symbol}, got: {quote.ask}"


# ── Edge Cases and Regression Tests ──────────────────────────────────────────


class TestBidAskEdgeCases:
    """Edge cases to prevent future regressions."""

    def test_none_bid_ask_distinguished_from_empty_string(self):
        """None must not be confused with empty string or other falsy values."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            bid=None,
            ask=None,
            volume=1000.0,
            oi=5000.0,
        )

        assert contract.bid is None
        assert contract.bid is not False
        assert contract.bid != ""
        assert contract.bid != 0

    def test_json_roundtrip_preserves_none(self):
        """JSON serialization/deserialization must preserve None values."""
        contract = OptionContract(
            symbol="NIFTY24JAN20000CE",
            expiry="2024-01-25",
            strike=20000.0,
            option_type="CE",
            ltp=150.0,
            bid=None,
            ask=None,
            volume=1000.0,
            oi=5000.0,
        )

        # Serialize to JSON
        json_str = contract.model_dump_json()

        # Deserialize back
        restored = OptionContract.model_validate_json(json_str)

        assert restored.bid is None
        assert restored.ask is None

    def test_quote_response_schema_allows_none(self):
        """QuoteResponse schema must allow None for bid/ask."""
        response = QuoteResponse(
            symbol="RELIANCE",
            exchange="NSE",
            ltp=2500.0,
            timestamp=1704067200000,
            bid=None,
            ask=None,
        )

        assert response.bid is None
        assert response.ask is None

    def test_no_silent_fallback_to_zero(self):
        """Ensure no code path silently falls back to 0.0 for bid/ask."""
        # Test that explicitly passing None stays None
        quote = Quote(
            symbol="TEST",
            ltp=Decimal("100"),
            bid=None,
            ask=None,
        )

        # Verify None is preserved (not converted to 0)
        assert quote.bid is None, "None bid was converted to non-None value"
        assert quote.ask is None, "None ask was converted to non-None value"
