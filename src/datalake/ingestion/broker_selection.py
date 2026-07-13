"""Pick the best broker gateway for a historical-data timeframe.

Reads each candidate gateway's real ``BrokerCapabilities.historical_windows``
(``gw.capabilities()``) instead of hardcoding broker names -- e.g. Dhan
currently offers up to 3650 days of 1-minute history vs Upstox's 30, but
that's data this function reads, not a special case it encodes. Stays
correct automatically if either broker's limits change.
"""

from __future__ import annotations

from typing import Any

# loader.py/schema.py use lowercase-suffix timeframe codes ("1h", "1d",
# "1w"); BrokerCapabilities.historical_windows uses the broker-facing
# codes ("60m", "1D", "1W"). Minute-based codes ("1m", "5m", ...) already
# match as-is -- only day/week/hour need translation. Do NOT blanket
# `.upper()` the whole string: "1m".upper() == "1M", which collides with
# the real "1M" (one month) timeframe.
_TIMEFRAME_ALIASES = {"1h": "60m", "1d": "1D", "1w": "1W"}


def select_historical_source(
    timeframe: str, gateways: dict[str, Any]
) -> tuple[str, Any]:
    """Return ``(broker_id, gateway)`` with the largest historical range
    for *timeframe* among *gateways*.

    Ties broken by ``max_chunk_days`` (fewer round-trips needed). Falls
    back to the first gateway in *gateways* if none declares a matching
    ``historical_windows`` entry, so this never blocks a sync -- it just
    stops being able to prefer one broker over another.
    """
    target_tf = _TIMEFRAME_ALIASES.get(timeframe, timeframe)

    best_id: str | None = None
    best_gw: Any = None
    best_key = (-1, -1)

    for broker_id, gw in gateways.items():
        try:
            windows = gw.capabilities().historical_windows
        except Exception:
            continue
        for window in windows:
            if window.timeframe != target_tf:
                continue
            key = (window.max_lookback_days, window.max_chunk_days)
            if key > best_key:
                best_id, best_gw, best_key = broker_id, gw, key
            break

    if best_gw is None:
        broker_id, gw = next(iter(gateways.items()))
        return broker_id, gw

    return best_id, best_gw
