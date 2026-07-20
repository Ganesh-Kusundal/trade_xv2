"""StreamMerger — merge bars + events into a single time-ordered stream.

Extracts the stream-merging responsibility from ``UnifiedReplayOrchestrator``.
Bars and events are merged into one deterministic total order (sorted by
``(timestamp, sequence)``) and can be projected back into a combined OHLCV
DataFrame for the replay engine.
"""

from __future__ import annotations

import pandas as pd

from analytics.replay.models import ReplayItem


class StreamMerger:
    """Merges bar and event ``ReplayItem`` streams."""

    def merge(self, bars: list[ReplayItem], events: list[ReplayItem]) -> list[ReplayItem]:
        """Merge bars and events into a single time-ordered stream."""
        return sorted(bars + events)

    def build_df(self, bar_items: list[ReplayItem]) -> pd.DataFrame:
        """Build a combined OHLCV DataFrame from bar items."""
        if not bar_items:
            return pd.DataFrame()

        rows = []
        for item in bar_items:
            if item.bar_data is not None:
                rows.append(item.bar_data)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df
