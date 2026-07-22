"""Simulation orchestration — fill pipeline, position meta, portfolio projection.

Re-exports from ``domain.simulation`` (canonical home for these pure-domain
constructs). Application-layer callers (analytics/paper, analytics/replay,
application/oms) import from here; domain consumers import from
``domain.simulation`` directly.
"""

from __future__ import annotations

# Re-export from domain.simulation (canonical home, REF-10).
from domain.simulation import (  # noqa: F401
    PortfolioProjector,
    PositionMeta,
    SimulationFillPipeline,
    project_trade,
)


__all__ = [
    "PortfolioProjector",
    "PositionMeta",
    "SimulationFillPipeline",
    "project_trade",
]
