"""Research and simulation orchestration (backtest, replay, paper, scanner).

ponytail: Physical package still lives at ``src/analytics/``; this module is the
target ownership boundary. Import ``analytics.*`` until the tree is moved here.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AnalyticsFacade",
    "create_backtest_engine",
    "create_paper_engine",
    "create_replay_engine",
]


def __getattr__(name: str) -> Any:
    """Lazy exports — avoids static import-linter application→runtime via facade."""
    if name == "AnalyticsFacade":
        return importlib.import_module("analytics.facade").Analytics
    if name == "create_backtest_engine":
        return importlib.import_module("analytics.engine_factory").create_backtest_engine
    if name == "create_paper_engine":
        return importlib.import_module("analytics.engine_factory").create_paper_engine
    if name == "create_replay_engine":
        return importlib.import_module("analytics.engine_factory").create_replay_engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
