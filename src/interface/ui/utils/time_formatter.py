"""Single canonical IST time formatter for CLI display.

Broker quote/order/trade timestamps are stored internally as UTC-aware
datetimes (see domain.ports.time_service) -- that's deliberate: it avoids
DST/comparison bugs and matches how Dhan/Upstox actually send timestamps
over the wire. Every place that *displays* a timestamp to a user watching
real IST market hours needs the same UTC -> IST conversion; this is the
one place that does it.
"""

from __future__ import annotations

from datetime import datetime

from domain.constants.market import IST_OFFSET


def format_ist_time(ts: datetime | None) -> str:
    """Format a timestamp as IST ``HH:MM:SS`` for display.

    Naive datetimes are assumed already-local and passed through
    unconverted. ``None`` renders as ``"N/A"``.
    """
    if ts is None:
        return "N/A"
    if ts.tzinfo is not None:
        ts = ts.astimezone(IST_OFFSET)
    return ts.strftime("%H:%M:%S")
