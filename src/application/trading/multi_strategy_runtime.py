"""Multi-strategy runtime — a thin holder for a strategy ``StrategyPipeline``.

This is a **strategy-pipeline holder**, not a trading executor. The
``TradingOrchestrator`` handles the full Scanner→Strategy→OMS flow.

The pipeline is injected by the composition root (``runtime.factory`` builds
it from the analytics strategy registry), so this module never imports
``analytics`` — it depends only on the domain ports. This preserves the
Application↛Analytics layering contract. Interface-layer callers that need to
discover/list strategies build the pipeline via
``runtime.factory.build_multi_strategy_runtime``.

.. note::
   Added by SM-19 (Phase 4a): documented as pipeline-holder, not
   competitor to the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MultiStrategyRuntime:
    """Hold a pre-built strategy pipeline and its strategy names.

    The pipeline is injected by the composition root (``runtime.factory``
    builds it from the analytics strategy registry), so this module never
    imports ``analytics`` — preserving the Application↛Analytics layering
    contract.
    """

    pipeline: Any = field(default=None)  # injected; a StrategyPipeline
    strategy_names: list[str] = field(default_factory=list)
    min_confidence: float = 0.7

    @property
    def strategies(self) -> list[Any]:
        """The strategy instances from the injected pipeline."""
        return list(self.pipeline.strategies)

    def list_strategies(self) -> list[str]:
        return list(self.strategy_names)
