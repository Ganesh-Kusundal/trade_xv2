"""Multi-strategy runtime — discover and build a StrategyPipeline from builtins.

This is a **strategy-pipeline builder**, not a trading executor.  The
``TradingOrchestrator`` handles the full Scanner→Strategy→OMS flow.
Runtime usage: ``trading_runtime_factory`` builds a pipeline here and
wires it into the orchestrator.

.. note::
   Added by SM-19 (Phase 4a): documented as pipeline-builder, not
   competitor to the orchestrator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from analytics.strategy.pipeline import StrategyPipeline
from analytics.strategy.registry import StrategyRegistry

logger = logging.getLogger(__name__)


@dataclass
class MultiStrategyRuntime:
    """Run multiple strategies through a shared StrategyPipeline."""

    strategy_names: list[str] = field(default_factory=list)
    min_confidence: float = 0.7

    def __post_init__(self) -> None:
        if not self.strategy_names:
            StrategyRegistry.discover("analytics.strategy.builtins")
            self.strategy_names = StrategyRegistry.list()
        self._pipeline = self._build_pipeline()

    def _build_pipeline(self) -> StrategyPipeline:
        strategies = []
        for name in self.strategy_names:
            try:
                strategies.append(StrategyRegistry.create(name))
            except KeyError:
                logger.warning("MultiStrategyRuntime: unknown strategy %s", name)
        return StrategyPipeline(strategies=strategies)

    @property
    def pipeline(self) -> StrategyPipeline:
        return self._pipeline

    def list_strategies(self) -> list[str]:
        return list(self.strategy_names)

    @classmethod
    def create_pipeline(cls, names: list[str]) -> StrategyPipeline:
        """Build a StrategyPipeline for the given strategy names."""
        return cls(strategy_names=names).pipeline
