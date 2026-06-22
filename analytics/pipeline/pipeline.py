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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from analytics.pipeline.features import Feature

logger = logging.getLogger(__name__)


@dataclass
class FeaturePipeline:
    """Chain of features computed sequentially on a DataFrame.

    Note: This pipeline intentionally has NO caching layer. An MD5-hash-based
    cache was previously removed because it introduced look-ahead bias in
    backtesting: overlapping time windows produce the same DataFrame hash
    but should produce different feature values (future data leaking into
    "past" computations). For repeated reads of static data, the caller
    should cache the DataFrame or results at the application layer with
    explicit time-boundary awareness.

    Attributes:
        features: List of Feature instances to compute
    """

    features: list[Feature] = field(default_factory=list, repr=False)

    def add(self, feature: Feature) -> FeaturePipeline:
        """Append a feature to the pipeline. Returns self for chaining."""
        self.features.append(feature)
        return self

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all features sequentially and return enriched DataFrame.

        Args:
            df: Input DataFrame with OHLCV data

        Returns:
            DataFrame enriched with feature columns
        """
        if df.empty:
            return df

        result = df.copy()
        for feature in self.features:
            try:
                result = feature.compute(result)
                logger.debug("Computed feature: %s", feature.name if hasattr(feature, "name") else type(feature).__name__)
            except Exception as exc:
                logger.warning("Feature %s failed: %s", type(feature).__name__, exc)

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

    def __len__(self) -> int:
        return len(self.features)

    def __repr__(self) -> str:
        names = [type(f).__name__ for f in self.features]
        return f"FeaturePipeline({', '.join(names)})"
