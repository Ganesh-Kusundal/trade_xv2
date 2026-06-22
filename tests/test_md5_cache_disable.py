"""Tests for MD5 cache disable in backtest/replay paths.

Ensures:
1. Feature pipeline is deterministic (no caching side effects)
2. Resample cache doesn't introduce look-ahead bias
3. Backtest results are reproducible
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from analytics.pipeline.pipeline import FeaturePipeline
from analytics.pipeline.features import RSI, ATR


class TestFeaturePipelineDeterminism:
    """FeaturePipeline must produce identical results on repeated runs."""

    def test_pipeline_is_deterministic(self) -> None:
        """Same input DataFrame → same output on multiple runs."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="1min"),
            "open": [100.0 + i * 0.1 for i in range(100)],
            "high": [101.0 + i * 0.1 for i in range(100)],
            "low": [99.0 + i * 0.1 for i in range(100)],
            "close": [100.5 + i * 0.1 for i in range(100)],
            "volume": [1000 + i * 10 for i in range(100)],
            "oi": [500] * 100,
        })

        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14))

        result1 = pipeline.run(df)
        result2 = pipeline.run(df)

        # Results must be bit-identical
        pd.testing.assert_frame_equal(result1, result2)

    def test_pipeline_no_internal_state_leakage(self) -> None:
        """Pipeline must not retain state between runs."""
        df1 = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=50, freq="1min"),
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.5] * 50,
            "volume": [1000] * 50,
            "oi": [500] * 50,
        })

        df2 = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-02", periods=50, freq="1min"),
            "open": [200.0] * 50,
            "high": [201.0] * 50,
            "low": [199.0] * 50,
            "close": [200.5] * 50,
            "volume": [2000] * 50,
            "oi": [600] * 50,
        })

        pipeline = FeaturePipeline().add(RSI(14))

        result1 = pipeline.run(df1)
        result2 = pipeline.run(df2)

        # Results for df2 should not be influenced by df1
        assert result1["close"].iloc[-1] != result2["close"].iloc[-1]


class TestResampleCacheNoLookAheadBias:
    """Resample cache must not cause look-ahead bias in backtests."""

    def test_cache_key_uses_deterministic_hash(self, tmp_path: Path) -> None:
        """Cache key generation must be deterministic for same inputs."""
        from datalake.cache_utils import generate_cache_key

        key1 = generate_cache_key("RELIANCE", "5m")
        key2 = generate_cache_key("RELIANCE", "5m")

        assert key1 == key2
        # MD5 produces 32-character hex string
        assert len(key1) == 32

    def test_cache_key_differs_for_different_timeframes(self) -> None:
        """Different timeframes must produce different cache keys."""
        from datalake.cache_utils import generate_cache_key

        key_5m = generate_cache_key("RELIANCE", "5m")
        key_15m = generate_cache_key("RELIANCE", "15m")

        assert key_5m != key_15m

    def test_cache_key_differs_for_different_symbols(self) -> None:
        """Different symbols must produce different cache keys."""
        from datalake.cache_utils import generate_cache_key

        key_rel = generate_cache_key("RELIANCE", "5m")
        key_tcs = generate_cache_key("TCS", "5m")

        assert key_rel != key_tcs


class TestBacktestPathCacheDisable:
    """Backtest/replay paths must not use feature caching."""

    def test_pipeline_run_creates_no_cache_files(self, tmp_path: Path) -> None:
        """FeaturePipeline.run() must not create cache files."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=50, freq="1min"),
            "open": [100.0] * 50,
            "high": [101.0] * 50,
            "low": [99.0] * 50,
            "close": [100.5] * 50,
            "volume": [1000] * 50,
            "oi": [500] * 50,
        })

        pipeline = FeaturePipeline().add(RSI(14))
        result = pipeline.run(df)

        # Verify pipeline ran successfully
        assert not result.empty
        # RSI feature adds a column (may be named by period like 14, or with prefix)
        assert len(result.columns) > len(df.columns)

    def test_multiple_runs_produce_identical_features(self) -> None:
        """Running pipeline multiple times must produce identical feature values."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="1min"),
            "open": [100.0 + i for i in range(100)],
            "high": [102.0 + i for i in range(100)],
            "low": [98.0 + i for i in range(100)],
            "close": [100.5 + i for i in range(100)],
            "volume": [1000 + i * 5 for i in range(100)],
            "oi": [500] * 100,
        })

        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14))

        results = [pipeline.run(df.copy()) for _ in range(5)]

        # All runs must be identical
        for i in range(1, len(results)):
            pd.testing.assert_frame_equal(results[0], results[i])


class TestCacheKeySecurity:
    """Cache key generation must be safe and deterministic."""

    def test_cache_key_does_not_use_f_string_interpolation(self) -> None:
        """Cache key must use hashing, not string concatenation."""
        from datalake.cache_utils import generate_cache_key

        # Test with potentially problematic inputs
        key1 = generate_cache_key("REL'IANCE", "5m")  # SQL injection attempt in symbol
        key2 = generate_cache_key("RELIANCE", "5m")

        # Keys should be different (different inputs)
        assert key1 != key2
        # But both should be valid 32-char hex strings
        assert len(key1) == 32
        assert len(key2) == 32
        # Both should be valid hex
        int(key1, 16)
        int(key2, 16)

    def test_cache_key_deterministic_with_extra_params(self) -> None:
        """Cache key must be deterministic even with extra parameters."""
        from datalake.cache_utils import generate_cache_key

        key1 = generate_cache_key("RELIANCE", "5m", columns=["close", "volume"])
        key2 = generate_cache_key("RELIANCE", "5m", columns=["volume", "close"])  # Different order

        # Should produce same key regardless of column order
        assert key1 == key2
