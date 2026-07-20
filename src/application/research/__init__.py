"""Research and simulation orchestration (backtest, replay, paper, scanner).

ponytail: Physical package still lives at ``src/analytics/``; this module is the
target ownership boundary. Import ``analytics.*`` until the tree is moved here.
"""

from __future__ import annotations

# Re-export the public analytics surface for callers migrating to this path.
from analytics.engine_factory import (
    create_backtest_engine,
    create_paper_engine,
    create_replay_engine,
)
from analytics.facade import AnalyticsFacade

__all__ = [
    "AnalyticsFacade",
    "create_backtest_engine",
    "create_paper_engine",
    "create_replay_engine",
]
