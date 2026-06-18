"""FeaturePipeline — composable feature computation engine.

Usage:
    pipeline = (
        FeaturePipeline()
        .add(ATR(14))
        .add(VWAP())
        .add(RSI(14))
        .add(RelativeVolume(20))
        .add(Trend())
    )
    features = pipeline.run(df)

With caching (for repeated queries on same data):
    pipeline = FeaturePipeline(enable_cache=True)
    result1 = pipeline.run(df)  # computes
    result2 = pipeline.run(df)  # returns cached result
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

import pandas as pd

from analytics.pipeline.features import Feature

logger = logging.getLogger(__name__)


@dataclass
class FeaturePipeline:
    """Chain of features computed sequentially on a DataFrame.
    
    The pipeline supports optional caching to avoid recomputing features
    for identical input DataFrames. This is useful in scenarios where
    the same data is queried multiple times (e.g., backtesting with
    overlapping windows, or repeated scanner runs).
    
    Caching uses MD5 hashing of the DataFrame JSON representation.
    When enabled, results are cached up to cache_max_size entries,
    with oldest entries evicted when the limit is reached.
    
    Attributes:
        features: List of Feature instances to compute
        enable_cache: Whether caching is active (default False)
        cache_max_size: Maximum number of cached entries (default 100)
    """

    features: list[Feature] = field(default_factory=list, repr=False)
    enable_cache: bool = False
    cache_max_size: int = 100
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    def add(self, feature: Feature) -> FeaturePipeline:
        """Append a feature to the pipeline. Returns self for chaining."""
        self.features.append(feature)
        return self

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all features sequentially and return enriched DataFrame.
        
        If caching is enabled, checks the cache first. On cache hit,
        returns a copy of the cached result. On cache miss, computes
        features and stores the result in the cache.
        
        Args:
            df: Input DataFrame with OHLCV data
            
        Returns:
            DataFrame enriched with feature columns
        """
        if df.empty:
            return df

        if self.enable_cache:
            df_hash = hashlib.md5(df.to_json().encode()).hexdigest()
            if df_hash in self._cache:
                logger.debug("Cache hit for FeaturePipeline.run()")
                return self._cache[df_hash].copy()

        result = df.copy()
        for feature in self.features:
            try:
                result = feature.compute(result)
                logger.debug("Computed feature: %s", feature.name if hasattr(feature, "name") else type(feature).__name__)
            except Exception as exc:
                logger.warning("Feature %s failed: %s", type(feature).__name__, exc)

        if self.enable_cache:
            if len(self._cache) >= self.cache_max_size:
                # Evict oldest entry
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                logger.debug("Cache evicted oldest entry, size=%d", len(self._cache))
            self._cache[df_hash] = result.copy()
            logger.debug("Cache stored, size=%d", len(self._cache))

        return result

    def feature_names(self) -> list[str]:
        """Return names of all features in the pipeline."""
        names = []
        for f in self.features:
            if hasattr(f, "name"):
                names.append(f.name)
            elif hasattr(f, "prefix"):
                names.append(f.prefix)
        return names

    def clear_cache(self) -> None:
        """Clear the feature computation cache."""
        self._cache.clear()
        logger.debug("FeaturePipeline cache cleared")

    def cache_size(self) -> int:
        """Return current number of cached entries."""
        return len(self._cache)

    def __len__(self) -> int:
        return len(self.features)

    def __repr__(self) -> str:
        names = [type(f).__name__ for f in self.features]
        cache_info = f", cache={len(self._cache)}" if self.enable_cache else ""
        return f"FeaturePipeline({', '.join(names)}{cache_info})"
