"""Strategy Protocol — duck-typed interface for all strategies.

A Strategy receives a Candidate and its feature-enriched DataFrame,
evaluates it, and returns a Signal.  This is the single interface used
by Scanner → Strategy → Replay → Backtest → Paper → Live.

Usage:
    class MyStrategy:
        @property
        def name(self) -> str:
            return "MyStrategy"

        def evaluate(self, candidate, features_df) -> Signal:
            # ... evaluate and return Signal
            pass
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal


@runtime_checkable
class Strategy(Protocol):
    """Protocol that every strategy must satisfy.

    A Strategy is a pure evaluator: it receives a Candidate and its
    features and returns a Signal.  It must NOT place orders, manage
    positions, or execute trades — that is the Execution layer's job.
    """

    @property
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    def evaluate(self, candidate: Candidate, features: pd.DataFrame) -> Signal:
        """Evaluate a single candidate and return a Signal.

        Parameters
        ----------
        candidate:
            The stock to evaluate (from a Scanner).
        features:
            Feature-enriched DataFrame for this symbol (output of FeaturePipeline).
            Columns may include ``rsi``, ``atr``, ``macd``, ``volume_sma``, etc.

        Returns
        -------
        Signal
            A Signal with signal_type, confidence, reasons, and optional
            entry/stop/target prices.
        """
        ...
