"""Production bridge: StrategyPipeline -> StrategyEvaluator port (Context 7)."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from analytics.scanner.models import Candidate
from analytics.strategy.pipeline import StrategyPipeline
from domain.constants import DEFAULT_EXCHANGE
from domain.models.features import FeatureSet
from domain.models.trading import CandidateDTO, SignalDTO


def _feature_set_to_df(fs: FeatureSet) -> pd.DataFrame:
    if fs.is_empty:
        return pd.DataFrame()
    df = pd.DataFrame(fs.columns)
    if fs.index:
        df.index = fs.index
    return df


def _to_dto(signal: object) -> SignalDTO:
    st = getattr(signal, "signal_type", "HOLD")
    st_val = st.value if hasattr(st, "value") else str(st)
    return SignalDTO(
        symbol=str(getattr(signal, "symbol", "")),
        exchange=str(getattr(signal, "exchange", DEFAULT_EXCHANGE)),
        side=st_val,
        signal_type=st_val,
        confidence=Decimal(str(getattr(signal, "confidence", 0))),
        quantity=int(getattr(signal, "quantity", 0) or 0),
        price=(
            Decimal(str(signal.entry_price))
            if getattr(signal, "entry_price", None) is not None
            else None
        ),
        entry_price=(
            Decimal(str(signal.entry_price))
            if getattr(signal, "entry_price", None) is not None
            else None
        ),
        strategy=str(getattr(signal, "strategy", "")),
        position_size_pct=Decimal(str(getattr(signal, "position_size_pct", 0) or 0)),
        metadata=getattr(signal, "metadata", None) or {},
    )


class StrategyPipelineEvaluator:
    """Adapts :class:`StrategyPipeline` to :class:`StrategyEvaluator`."""

    def __init__(self, pipeline: StrategyPipeline) -> None:
        self._pipeline = pipeline

    def evaluate_single(self, candidate: CandidateDTO, features: FeatureSet) -> list[SignalDTO]:
        legacy = Candidate(
            symbol=candidate.symbol,
            score=float(candidate.score),
            reasons=candidate.reasons,
            metrics={k: float(v) for k, v in candidate.metrics.items()},
        )
        df = _feature_set_to_df(features)
        signals = self._pipeline.evaluate_single(legacy, df)
        return [_to_dto(s) for s in signals]


__all__ = ["StrategyPipelineEvaluator"]
