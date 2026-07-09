"""Tests for fill model (current_close vs next_open) in backtest."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from analytics.replay.models import (
    FillModel,
    ReplayConfig,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build OHLCV DataFrame from list of dicts."""
    return pd.DataFrame(rows)


def _stub_rows() -> list[dict]:
    """Generate 10 bars of OHLCV data with distinct opens."""
    base = datetime(2024, 1, 1)
    return [
        {
            "timestamp": base,
            "open": 100.0 + i * 2,
            "high": 105.0 + i * 2,
            "low": 95.0 + i * 2,
            "close": 102.0 + i * 2,
            "volume": 1000,
        }
        for i in range(10)
    ]


class TestFillModelEnum:
    """Verify FillModel enum values."""

    def test_current_close(self):
        assert FillModel.CURRENT_CLOSE == "current_close"

    def test_next_open(self):
        assert FillModel.NEXT_OPEN == "next_open"

    def test_default_in_config(self):
        config = ReplayConfig()
        assert config.fill_model == FillModel.NEXT_OPEN


class TestFillModelConfig:
    """Verify ReplayConfig accepts fill_model field."""

    def test_set_next_open(self):
        config = ReplayConfig(fill_model=FillModel.NEXT_OPEN)
        assert config.fill_model == FillModel.NEXT_OPEN

    def test_set_current_close(self):
        config = ReplayConfig(fill_model=FillModel.CURRENT_CLOSE)
        assert config.fill_model == FillModel.CURRENT_CLOSE

    def test_backward_compatible_default(self):
        """Default config uses next-bar-open fills (no look-ahead)."""
        config = ReplayConfig()
        assert config.fill_model == FillModel.NEXT_OPEN
        assert config.slippage_pct == 0.0
        assert config.commission_flat == 0.0
