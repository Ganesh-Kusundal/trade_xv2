"""Tests for feature builder."""

from __future__ import annotations

import pytest

from analytics.core.feature_builder import FeatureBuilder

from .helpers import prices


class TestFeatureBuilder:
    def test_basic(self) -> None:
        df = prices(30)
        builder = FeatureBuilder()
        result = builder.build(df)
        assert result is not None
        assert hasattr(result, "data")
        assert hasattr(result, "features")
