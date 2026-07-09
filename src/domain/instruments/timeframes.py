"""Timeframe aliases (TradeHull / human → canonical history TF).

Canonical forms used by :meth:`Instrument.history` / DataProvider:
``1m``, ``5m``, ``15m``, ``30m``, ``60m``/``1h``, ``1D``, etc.
"""

from __future__ import annotations

# TradeHull-style and common aliases → platform timeframe
_TF_MAP: dict[str, str] = {
    "1": "1m",
    "1m": "1m",
    "1min": "1m",
    "1MINUTE": "1m",
    "3": "3m",
    "3m": "3m",
    "5": "5m",
    "5m": "5m",
    "5min": "5m",
    "15": "15m",
    "15m": "15m",
    "15min": "15m",
    "25": "25m",
    "25m": "25m",
    "30": "30m",
    "30m": "30m",
    "60": "60m",
    "60m": "60m",
    "1h": "60m",
    "1H": "60m",
    "HOUR": "60m",
    "DAY": "1D",
    "DAILY": "1D",
    "1D": "1D",
    "D": "1D",
    "1d": "1D",
    "WEEK": "1W",
    "1W": "1W",
    "1w": "1W",
}


def normalize_timeframe(timeframe: str) -> str:
    """Map TradeHull / human timeframe to platform form.

    Raises
    ------
    ValueError
        If ``timeframe`` is empty or unknown.
    """
    raw = str(timeframe).strip()
    if not raw:
        raise ValueError("Empty timeframe")
    key = raw.upper() if raw.upper() in _TF_MAP else raw
    # try exact, then upper, then lower
    if raw in _TF_MAP:
        return _TF_MAP[raw]
    if raw.upper() in _TF_MAP:
        return _TF_MAP[raw.upper()]
    if raw.lower() in _TF_MAP:
        return _TF_MAP[raw.lower()]
    # already looks like platform form (e.g. 2h) — pass through
    if len(raw) >= 2 and raw[-1] in "mhdDwW" and raw[:-1].isdigit():
        return raw if raw[-1] != "d" else raw[:-1] + "D"
    raise ValueError(
        f"Unknown timeframe {timeframe!r}. "
        f"Supported aliases include: {', '.join(sorted(set(_TF_MAP.values())))}."
    )
