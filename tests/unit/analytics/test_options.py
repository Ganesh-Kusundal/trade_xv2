"""Tests for options analytics."""

from __future__ import annotations

from analytics.options._greeks import GreeksAnalytics
from analytics.options.options_analytics import (
    IVAnalytics,
    MaxPainAnalytics,
    OpenInterestAnalytics,
    OptionFlowAnalytics,
    PCRAnalytics,
    StrikeAnalytics,
)

from .helpers import option_chain


class TestOpenInterestAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = OpenInterestAnalytics().analyze(chain)
        assert "highest_call_oi" in result.metrics


class TestPCRAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = PCRAnalytics().analyze(chain)
        assert "pcr" in result.metrics


class TestMaxPainAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = MaxPainAnalytics().analyze(chain)
        assert "current_max_pain" in result.metrics


class TestIVAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = IVAnalytics().analyze(chain)
        assert "current_iv" in result.metrics


class TestStrikeAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = StrikeAnalytics().analyze(chain)
        assert result.name == "strikes"


class TestOptionFlowAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = OptionFlowAnalytics().analyze(chain)
        assert result.name == "option_flow"


class TestGreeksAnalytics:
    def test_basic(self) -> None:
        chain = option_chain()
        result = GreeksAnalytics().analyze(chain)
        assert result.name == "greeks"
