"""DEPRECATED — moved to analytics.backtest.fast_backtest.

This module no longer re-exports analytics types (that would re-create
the datalake → analytics import cycle). Use the analytics package path::

    analytics.backtest.fast_backtest.FastBacktestEngine
    # or analytics.backtest.FastBacktestEngine
"""

from __future__ import annotations

raise ImportError(
    "datalake.research.fast_backtest has moved to analytics.backtest.fast_backtest. "
    "Use analytics.backtest.FastBacktestEngine instead."
)
