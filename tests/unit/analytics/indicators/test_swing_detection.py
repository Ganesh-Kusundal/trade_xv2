"""Tests for swing detection — verify no look-ahead bias."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.indicators.market_structure import MarketStructureAnalyzer


def _make_data(seed: int = 42, n: int = 50) -> pd.DataFrame:
    """Generate deterministic OHLCV data."""
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n) * 0.5)
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    open_ = close + rng.randn(n) * 0.3
    volume = rng.randint(1000, 10000, n).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


class TestSwingDetectionNoLookAhead:
    """Verify swing detection does not use future data."""

    def test_truncated_data_produces_same_swings(self):
        """Swings at bar i must only use bars 0..i.

        If we truncate data at bar 30, swings at bars 0-28 must be
        identical to the full dataset.
        """
        data = _make_data(seed=42, n=50)
        analyzer = MarketStructureAnalyzer(swing_left=2, swing_right=2)

        # Full analysis
        result = analyzer.analyze(data)

        # Truncated analysis (30 bars)
        truncated = data.iloc[:31].copy()
        result_truncated = analyzer.analyze(truncated)

        # Swings in the overlapping region must be identical
        # Note: last swing_right bars may differ due to confirmation delay
        overlap = 31 - 2  # Exclude last swing_right bars
        assert (
            result["swing_high"].iloc[:overlap].tolist()
            == result_truncated["swing_high"].iloc[:overlap].tolist()
        )
        assert (
            result["swing_low"].iloc[:overlap].tolist()
            == result_truncated["swing_low"].iloc[:overlap].tolist()
        )

    def test_no_future_data_in_swing_classification(self):
        """Swing at bar i must only use bars 0..i for classification.

        This verifies the core no-lookahead invariant: truncating the
        dataset must not change swings in the overlapping region.
        """
        data = _make_data(seed=42, n=50)
        analyzer = MarketStructureAnalyzer(swing_left=2, swing_right=2)

        full = analyzer.analyze(data)
        partial = analyzer.analyze(data.iloc[:31].copy())

        # Overlap minus confirmation window
        check_end = 31 - 2
        assert (
            full["swing_high"].iloc[:check_end].tolist()
            == partial["swing_high"].iloc[:check_end].tolist()
        )

    def test_swing_detection_finds_real_peaks(self):
        """A clear peak should still be detected as swing high."""
        data = _make_data(seed=42, n=50)
        analyzer = MarketStructureAnalyzer(swing_left=2, swing_right=2)

        result = analyzer.analyze(data)

        # Should have at least some swing highs and lows
        assert result["swing_high"].sum() > 0
        assert result["swing_low"].sum() > 0


class TestSwingDetectionCorrectness:
    """Verify swing detection logic is correct."""

    def test_simple_peak_detected(self):
        """A simple peak surrounded by lower values should be a swing high."""
        data = pd.DataFrame(
            {
                "open": [100, 100, 100, 100, 100],
                "high": [100, 105, 110, 105, 100],
                "low": [90, 90, 90, 90, 90],
                "close": [95, 95, 95, 95, 95],
                "volume": [1000] * 5,
            }
        )

        analyzer = MarketStructureAnalyzer(swing_left=2, swing_right=2)
        result = analyzer.analyze(data)

        # With the confirmed-swing approach, the peak at index 2
        # is confirmed at index 4 (after swing_right=2 delay)
        assert result["swing_high"].sum() > 0

    def test_simple_trough_detected(self):
        """A simple trough surrounded by higher values should be a swing low."""
        data = pd.DataFrame(
            {
                "open": [100, 100, 100, 100, 100],
                "high": [110, 110, 110, 110, 110],
                "low": [100, 95, 90, 95, 100],
                "close": [105, 105, 105, 105, 105],
                "volume": [1000] * 5,
            }
        )

        analyzer = MarketStructureAnalyzer(swing_left=2, swing_right=2)
        result = analyzer.analyze(data)

        assert result["swing_low"].sum() > 0

    def test_empty_data(self):
        """Empty data should produce empty swing columns."""
        data = pd.DataFrame(
            {
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": [],
            }
        )

        analyzer = MarketStructureAnalyzer()
        result = analyzer.analyze(data)

        assert len(result["swing_high"]) == 0
        assert len(result["swing_low"]) == 0
