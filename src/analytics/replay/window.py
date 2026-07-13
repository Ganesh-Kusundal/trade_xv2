"""Circular-buffer window management for ReplayEngine.

P5.2: Implements bounded deque for window storage with O(window_size)
memory regardless of input dataset size. Uses pre-allocated numpy arrays
as a circular buffer (ring buffer) with modular indexing.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from domain.candles.historical import HistoricalBar


def new_window_state(window_size: int) -> dict:
    """Create per-symbol sliding window state."""
    if window_size > 0:
        return {
            "size": window_size,
            "open": np.empty(window_size, dtype=np.float64),
            "high": np.empty(window_size, dtype=np.float64),
            "low": np.empty(window_size, dtype=np.float64),
            "close": np.empty(window_size, dtype=np.float64),
            "volume": np.empty(window_size, dtype=np.float64),
            "symbol": np.empty(window_size, dtype=object),
            "timestamp": np.empty(window_size, dtype="datetime64[ns]"),
            "filled": 0,
            "head": 0,
        }
    return {"size": 0, "data": deque()}


def append_bar(state: dict, bar: HistoricalBar) -> None:
    """Append a bar to per-symbol window state (O(1) ring buffer)."""
    window_size = state["size"]
    if window_size > 0:
        widx = state["head"]
        state["open"][widx] = bar.open
        state["high"][widx] = bar.high
        state["low"][widx] = bar.low
        state["close"][widx] = bar.close
        state["volume"][widx] = bar.volume
        state["symbol"][widx] = bar.symbol
        state["timestamp"][widx] = bar.timestamp
        if state["filled"] < window_size:
            state["filled"] += 1
        state["head"] = (state["head"] + 1) % window_size
    else:
        state["data"].append(bar.to_dict())


def to_dataframe(state: dict) -> pd.DataFrame:
    """Build a feature-pipeline window DataFrame from per-symbol state."""
    window_size = state["size"]
    if window_size > 0:
        filled = state["filled"]
        if filled < window_size:
            return pd.DataFrame({
                "open": state["open"][:filled],
                "high": state["high"][:filled],
                "low": state["low"][:filled],
                "close": state["close"][:filled],
                "volume": state["volume"][:filled],
                "symbol": state["symbol"][:filled],
                "timestamp": state["timestamp"][:filled],
            })
        head = state["head"]
        idx = np.arange(head - window_size, head) % window_size
        return pd.DataFrame({
            "open": state["open"][idx],
            "high": state["high"][idx],
            "low": state["low"][idx],
            "close": state["close"][idx],
            "volume": state["volume"][idx],
            "symbol": state["symbol"][idx],
            "timestamp": state["timestamp"][idx],
        })
    return pd.DataFrame(state["data"])


def build_window(window_data, window_size: int) -> pd.DataFrame:
    """Build a DataFrame from the window data (deprecated by REF-022 ring buffer).

    Retained for backward compatibility with external callers.
    """
    if isinstance(window_data, list) and window_size > 0:
        window_data = window_data[-window_size:]
    return pd.DataFrame(window_data)
