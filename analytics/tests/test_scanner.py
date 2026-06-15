"""Tests for scanner and ranking."""

from __future__ import annotations

import pytest

from analytics.ranking.ranking import RankingEngine
from analytics.scanner.scanners import MomentumScanner

from .helpers import prices


class TestRanking:
    def test_basic(self) -> None:
        df = prices(30)
        df["score"] = [i * 10 for i in range(30)]
        result = RankingEngine().analyze(df, name="ranking")
        assert result.name == "ranking"


class TestScanner:
    def test_momentum_scanner(self) -> None:
        df = prices(30)
        scanner = MomentumScanner()
        result = scanner.scan(df)
        assert result is not None
