"""Tests for volume-weighted slippage model in backtest."""

from __future__ import annotations

from unittest.mock import MagicMock

from analytics.replay.models import (
    ReplayConfig,
    SlippageModel,
)

# ── SlippageModel Enum Tests ──────────────────────────────────────────


class TestSlippageModelEnum:
    """Verify SlippageModel enum values."""

    def test_fixed_pct_value(self):
        assert SlippageModel.FIXED_PCT == "fixed_pct"

    def test_volume_weighted_value(self):
        assert SlippageModel.VOLUME_WEIGHTED == "volume_weighted"


# ── Config Default Tests ──────────────────────────────────────────────


class TestConfigDefaults:
    """Verify ReplayConfig defaults for slippage model."""

    def test_default_slippage_model(self):
        config = ReplayConfig()
        assert config.slippage_model == SlippageModel.FIXED_PCT

    def test_default_avg_volume(self):
        config = ReplayConfig()
        assert config.avg_volume == 0.0

    def test_default_slippage_pct(self):
        config = ReplayConfig()
        assert config.slippage_pct == 0.0


# ── Config Custom Tests ───────────────────────────────────────────────


class TestConfigCustom:
    """Verify ReplayConfig accepts custom slippage model settings."""

    def test_volume_weighted_model(self):
        config = ReplayConfig(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.05,
            avg_volume=100000,
        )
        assert config.slippage_model == SlippageModel.VOLUME_WEIGHTED
        assert config.slippage_pct == 0.05
        assert config.avg_volume == 100000

    def test_fixed_pct_model_explicit(self):
        config = ReplayConfig(
            slippage_model=SlippageModel.FIXED_PCT,
            slippage_pct=0.1,
        )
        assert config.slippage_model == SlippageModel.FIXED_PCT
        assert config.slippage_pct == 0.1


# ── Engine Slippage Computation Tests ──────────────────────────────────


class TestEngineSlippageComputation:
    """Verify _compute_slippage_pct method on ReplayEngine."""

    def _make_engine(self, **kwargs):
        from analytics.replay.engine import ReplayEngine

        config = ReplayConfig(**kwargs)
        return ReplayEngine(config=config, oms_adapter=MagicMock())

    def test_fixed_pct_returns_base_slippage(self):
        engine = self._make_engine(
            slippage_model=SlippageModel.FIXED_PCT,
            slippage_pct=0.05,
        )
        result = engine._compute_slippage_pct(bar_volume=100000)
        assert result == 0.05

    def test_volume_weighted_high_volume(self):
        """High volume should produce less slippage."""
        engine = self._make_engine(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.1,
            avg_volume=100000,
        )
        result = engine._compute_slippage_pct(bar_volume=200000)
        assert result == 0.05  # 0.1 * (100000/200000)

    def test_volume_weighted_low_volume(self):
        """Low volume should produce more slippage."""
        engine = self._make_engine(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.1,
            avg_volume=100000,
        )
        result = engine._compute_slippage_pct(bar_volume=50000)
        assert result == 0.2  # 0.1 * (100000/50000)

    def test_volume_weighted_equal_volume(self):
        """Volume equal to avg should return base slippage."""
        engine = self._make_engine(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.1,
            avg_volume=100000,
        )
        result = engine._compute_slippage_pct(bar_volume=100000)
        assert result == 0.1

    def test_volume_weighted_zero_bar_volume(self):
        """Zero bar volume should fall back to base slippage."""
        engine = self._make_engine(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.1,
            avg_volume=100000,
        )
        result = engine._compute_slippage_pct(bar_volume=0)
        assert result == 0.1

    def test_volume_weighted_zero_avg_volume(self):
        """Zero avg volume should fall back to base slippage."""
        engine = self._make_engine(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.1,
            avg_volume=0,
        )
        result = engine._compute_slippage_pct(bar_volume=100000)
        assert result == 0.1

    def test_volume_weighted_zero_slippage(self):
        """Zero base slippage should always return zero."""
        engine = self._make_engine(
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            slippage_pct=0.0,
            avg_volume=100000,
        )
        result = engine._compute_slippage_pct(bar_volume=50000)
        assert result == 0.0
