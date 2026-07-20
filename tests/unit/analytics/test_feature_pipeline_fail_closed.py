"""Feature pipeline fail-closed behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.pipeline.errors import FeaturePipelineError
from analytics.pipeline.features import Feature
from analytics.pipeline.pipeline import FeaturePipeline


class _BrokenFeature(Feature):
    name = "broken"

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        raise ValueError("indicator failed")


def test_fail_closed_raises() -> None:
    pipeline = FeaturePipeline(features=[_BrokenFeature()], fail_closed=True)
    with pytest.raises(FeaturePipelineError, match="broken"):
        pipeline.run(pd.DataFrame({"close": [1.0, 2.0, 3.0]}))


def test_fail_open_swallows() -> None:
    pipeline = FeaturePipeline(features=[_BrokenFeature()], fail_closed=False)
    result = pipeline.run(pd.DataFrame({"close": [1.0, 2.0, 3.0]}))
    assert len(result) == 3
