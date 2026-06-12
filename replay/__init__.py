"""Replay module -- historical market data replay.

Provides a simple replay engine that iterates over historical bars
in chronological order, invoking a callback for each bar.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict, List


class MarketReplay:
    """Replays a sequence of historical market bars.

    Parameters
    ----------
    bars:
        A list of bar dicts (e.g. OHLCV data) to replay in order.
    """

    def __init__(self, bars: list[dict[str, Any]]) -> None:
        self._bars = list(bars)

    def replay(self, callback: Callable[[dict[str, Any]], None]) -> int:
        """Invoke *callback(bar)* for each bar in sequence.

        Returns the number of bars replayed.
        """
        count = 0
        for bar in self._bars:
            callback(bar)
            count += 1
        return count
