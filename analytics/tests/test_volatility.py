"""Tests for volatility analytics."""

from __future__ import annotations

import pytest

from analytics.volatility.volatility_analytics import VolatilityAnalytics

from .helpers import prices


class TestVolatilityAnalytics:
    def test_basic(self) -> None:
        df = prices(30)
        result = VolatilityAnalytics().analyze("TEST", df)
        assert result.name == "volatility"
