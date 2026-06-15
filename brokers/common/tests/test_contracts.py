"""Contract tests — runs against both Dhan and Upstox.

Same test, same expectations, broker-agnostic.
"""

from __future__ import annotations

import pytest
import pandas as pd
from decimal import Decimal

from brokers.common.data_contracts import (
    HISTORICAL_COLUMNS,
    QUOTE_FIELDS,
    OPTION_CHAIN_COLUMNS,
    FUTURE_CHAIN_COLUMNS,
    validate_historical_df,
    validate_no_forbidden_fields,
    Quote,
    MarketDepth,
    Position,
    Holding,
    FundLimits,
    Trade,
)


class TestHistoricalSchema:
    """Validate historical DataFrame schema."""

    def test_columns(self):
        assert HISTORICAL_COLUMNS == [
            "timestamp", "open", "high", "low", "close",
            "volume", "oi", "symbol", "exchange", "timeframe"
        ]

    def test_no_forbidden_columns(self):
        forbidden = ["security_id", "instrument_token", "exchange_token", "symbol_token"]
        for col in forbidden:
            assert col not in HISTORICAL_COLUMNS


class TestQuoteSchema:
    """Validate Quote dataclass schema."""

    def test_fields(self):
        assert QUOTE_FIELDS == [
            "symbol", "ltp", "open", "high", "low", "close",
            "volume", "change", "bid", "ask", "timestamp"
        ]

    def test_no_forbidden_fields(self):
        q = Quote(symbol="TCS", ltp=Decimal("100"))
        assert validate_no_forbidden_fields(q)


class TestMarketDepthSchema:
    """Validate MarketDepth dataclass schema."""

    def test_no_forbidden_fields(self):
        d = MarketDepth()
        assert validate_no_forbidden_fields(d)


class TestPositionSchema:
    """Validate Position dataclass schema."""

    def test_no_forbidden_fields(self):
        p = Position(symbol="TCS", exchange="NSE")
        assert validate_no_forbidden_fields(p)


class TestHoldingSchema:
    """Validate Holding dataclass schema."""

    def test_no_forbidden_fields(self):
        h = Holding(symbol="TCS", exchange="NSE")
        assert validate_no_forbidden_fields(h)


class TestFundLimitsSchema:
    """Validate FundLimits dataclass schema."""

    def test_no_forbidden_fields(self):
        f = FundLimits()
        assert validate_no_forbidden_fields(f)


class TestTradeSchema:
    """Validate Trade dataclass schema."""

    def test_no_forbidden_fields(self):
        t = Trade(trade_id="T1", order_id="O1", symbol="TCS", exchange="NSE", side="BUY", quantity=10)
        assert validate_no_forbidden_fields(t)


class TestOptionChainSchema:
    """Validate option chain DataFrame schema."""

    def test_columns(self):
        assert OPTION_CHAIN_COLUMNS == [
            "expiry", "strike", "option_type", "ltp", "volume", "oi", "iv"
        ]


class TestFutureChainSchema:
    """Validate future chain DataFrame schema."""

    def test_columns(self):
        assert FUTURE_CHAIN_COLUMNS == [
            "expiry", "ltp", "volume", "oi", "change"
        ]
