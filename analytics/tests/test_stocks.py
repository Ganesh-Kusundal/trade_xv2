"""Tests for stock and futures analytics."""

from __future__ import annotations

import pytest

from analytics.features.volume import VolumeAnalytics
from analytics.features.relative_strength import RelativeStrengthAnalyzer
from analytics.futures.futures_analytics import FuturesAnalytics
from analytics.stocks.stock_analytics import StockAnalytics

from .helpers import prices


class TestVolumeAnalytics:
    def test_basic(self) -> None:
        df = prices(30)
        result = VolumeAnalytics().analyze(df)
        assert "relative_volume" in result.metrics


class TestRelativeStrength:
    def test_basic(self) -> None:
        df = prices(30)
        result = RelativeStrengthAnalyzer().analyze("TEST", df, benchmark_prices=df)
        assert result.name == "relative_strength"


class TestFuturesAnalytics:
    def test_basic(self) -> None:
        result = FuturesAnalytics().analyze("TEST", spot_price=100, future_price=102)
        assert result.name == "future"


class TestStockAnalytics:
    def test_basic(self) -> None:
        df = prices(30)
        result = StockAnalytics().analyze("TEST", df)
        assert result.name == "stock"
