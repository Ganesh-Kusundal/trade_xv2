"""StrategyEvaluator bridge parity — pipeline vs port produce equivalent signals."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from analytics.scanner.models import Candidate
from analytics.strategy.evaluator_bridge import StrategyPipelineEvaluator
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.pipeline import StrategyPipeline
from domain.models.features import FeatureSet
from domain.models.trading import CandidateDTO


class _AlwaysBuy:
    name = "always_buy"

    def evaluate(self, candidate, features):
        return Signal(
            symbol=candidate.symbol,
            signal_type=SignalType.BUY,
            confidence=0.85,
            strategy=self.name,
        )


def test_evaluator_bridge_matches_direct_pipeline() -> None:
    pipeline = StrategyPipeline(strategies=[_AlwaysBuy()])
    bridge = StrategyPipelineEvaluator(pipeline)

    df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    legacy = Candidate(symbol="RELIANCE", score=50.0, reasons=["test"])
    direct = pipeline.evaluate_single(legacy, df)

    dto = CandidateDTO(
        symbol="RELIANCE",
        exchange="NSE",
        score=Decimal("50"),
        reasons=["test"],
    )
    fs = FeatureSet(columns=df.to_dict(orient="list"), index=list(df.index))
    via_port = bridge.evaluate_single(dto, fs)

    assert len(direct) == len(via_port)
    assert direct[0].symbol == via_port[0].symbol
    assert str(direct[0].signal_type).upper().endswith("BUY")
    assert via_port[0].signal_type.upper().endswith("BUY")
    assert float(via_port[0].confidence) == pytest.approx(float(direct[0].confidence))
