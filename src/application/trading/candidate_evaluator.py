"""Candidate evaluation — fetch features and run the strategy pipeline.

Extracted from ``TradingOrchestrator`` to separate the analytics
gating (feature fetching + strategy evaluation) from execution concerns.
"""

from __future__ import annotations

import logging

from application.trading.models import FeatureFetcher
from domain.models.features import FeatureSet
from domain.models.trading import CandidateDTO, SignalDTO
from domain.ports.strategy_evaluator import StrategyEvaluator

logger = logging.getLogger(__name__)


class CandidateEvaluator:
    """Fetches features and evaluates candidates through the strategy pipeline.

    Responsibilities
    ----------------
    - Feature fetching with optional timeout
    - Strategy evaluation via the :class:`StrategyEvaluator` port

    Parameters
    ----------
    feature_fetcher:
        Provides raw feature data for a symbol.
    strategy_evaluator:
        Evaluates a candidate with pre-computed features.
    feature_timeout_seconds:
        Maximum seconds to wait for feature fetching. ``None`` = no limit.
    """

    def __init__(
        self,
        feature_fetcher: FeatureFetcher,
        strategy_evaluator: StrategyEvaluator,
        feature_timeout_seconds: float | None = None,
    ) -> None:
        self._feature_fetcher = feature_fetcher
        self._strategy_evaluator = strategy_evaluator
        self._feature_timeout_seconds = feature_timeout_seconds

    def fetch_features(self, symbol: str) -> FeatureSet | None:
        """Fetch feature data for a *symbol*.

        Returns
        -------
        FeatureSet | None:
            Feature set, or ``None`` if the fetch failed or timed out.
        """
        try:
            if self._feature_timeout_seconds is not None:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._feature_fetcher.fetch, symbol)
                    return future.result(timeout=self._feature_timeout_seconds)
            else:
                return self._feature_fetcher.fetch(symbol)
        except Exception as exc:
            logger.exception("Feature fetch error for %s: %s", symbol, exc)
            return None

    def evaluate_candidate(
        self,
        candidate: CandidateDTO,
        features: FeatureSet,
    ) -> list[SignalDTO]:
        """Evaluate *candidate* through the strategy pipeline.

        Returns
        -------
        list[SignalDTO]:
            Signals from all strategies (may include non-actionable HOLD signals).
        """
        try:
            signals = self._strategy_evaluator.evaluate_single(candidate, features)
            from application.trading.signal_coordinator import coalesce_strategy_signals

            signals = coalesce_strategy_signals(signals)
            logger.info(
                "Evaluated %s: %d signals generated",
                candidate.symbol,
                len(signals),
            )
            return signals
        except Exception as exc:
            logger.exception(
                "Strategy evaluation failed for %s: %s",
                candidate.symbol,
                exc,
            )
            return []
