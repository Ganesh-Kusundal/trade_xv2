"""DEPRECATED — moved to analytics.backtest.run_backtest.

This module no longer re-exports analytics runners (that would re-create
the datalake → analytics import cycle). Run via::

    python -m analytics.backtest.run_backtest --symbol RELIANCE
"""

from __future__ import annotations

raise ImportError(
    "datalake.research.run_backtest has moved to analytics.backtest.run_backtest. "
    "Use: python -m analytics.backtest.run_backtest"
)
