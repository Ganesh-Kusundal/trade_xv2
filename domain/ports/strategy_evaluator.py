"""Strategy evaluation port — decouples execution from analytics."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from domain.models.trading import CandidateDTO, SignalDTO


@runtime_checkable
class StrategyEvaluator(Protocol):
    """Evaluate a candidate with pre-computed features."""

    def evaluate_single(
        self, candidate: CandidateDTO, features: pd.DataFrame
    ) -> list[SignalDTO]: ...


__all__ = ["StrategyEvaluator"]
