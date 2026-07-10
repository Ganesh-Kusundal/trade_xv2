"""Tests for feature builder."""

from __future__ import annotations

from analytics.core.feature_builder import FeatureBuilder
from analytics.pipeline.features import Beta, Correlation, PercentRank, ZScore

from .helpers import prices


class TestFeatureBuilder:
    def test_basic(self) -> None:
        df = prices(30)
        builder = FeatureBuilder()
        result = builder.build(df)
        assert result is not None
        assert hasattr(result, "data")
        assert hasattr(result, "features")


class TestZScore:
    def test_zscore_basic(self) -> None:
        df = prices(30)
        z = ZScore(period=10)
        result = z.compute(df)
        assert "z_score" in result.columns
        assert len(result) == len(df)

    def test_zscore_custom_source(self) -> None:
        df = prices(30)
        df["custom"] = df["close"] * 1.1
        z = ZScore(source="custom", period=10)
        result = z.compute(df)
        assert "z_score" in result.columns


class TestCorrelation:
    def test_correlation_basic(self) -> None:
        df = prices(30)
        c = Correlation(period=10)
        result = c.compute(df)
        assert "correlation" in result.columns
        assert len(result) == len(df)

    def test_correlation_custom_sources(self) -> None:
        df = prices(30)
        df["signal1"] = df["close"].shift(1)
        df["signal2"] = df["volume"] * 0.5
        c = Correlation(source1="signal1", source2="signal2", period=10)
        result = c.compute(df)
        assert "correlation" in result.columns


class TestBeta:
    def test_beta_requires_benchmark(self) -> None:
        df = prices(100)
        beta = Beta(asset_col="close", bench_col="benchmark", period=20)
        try:
            beta.compute(df)
            raise AssertionError("Should have raised ValueError for missing benchmark column")
        except ValueError as e:
            assert "benchmark" in str(e)

    def test_beta_basic(self) -> None:
        df = prices(100)
        df["benchmark"] = df["close"] * 0.8 + 10
        beta = Beta(asset_col="close", bench_col="benchmark", period=20)
        result = beta.compute(df)
        assert "beta" in result.columns
        assert len(result) == len(df)


class TestPercentRank:
    def test_percent_rank_basic(self) -> None:
        df = prices(100)
        pr = PercentRank(period=20)
        result = pr.compute(df)
        assert "pct_rank" in result.columns
        assert len(result) == len(df)

    def test_percent_rank_values_in_range(self) -> None:
        df = prices(100)
        pr = PercentRank(period=20)
        result = pr.compute(df)
        # Percent rank should be 0-100
        assert result["pct_rank"].max() <= 100.0
        assert result["pct_rank"].min() >= 0.0
