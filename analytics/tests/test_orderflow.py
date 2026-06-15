"""Tests for orderflow and probability."""

from __future__ import annotations

import pytest

from analytics.orderflow.orderflow import OrderFlowAnalytics
from analytics.probability.probability import ProbabilityEngine

from .helpers import trades, prices


class TestOrderFlow:
    def test_basic(self) -> None:
        df = trades()
        result = OrderFlowAnalytics().analyze(df)
        assert result.name == "order_flow"


class TestProbability:
    def test_basic(self) -> None:
        metrics = {"rsi": 50, "momentum": 0.5, "volume": 1000}
        result = ProbabilityEngine().analyze(metrics)
        assert result.name == "probability"
