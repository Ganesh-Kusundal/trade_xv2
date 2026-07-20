"""WebSocket constants — reconnect, staleness, and streaming configuration.

All constants governing WebSocket connection behavior, including reconnection
attempts, staleness thresholds, and streaming limits.
"""

from __future__ import annotations

# ── Dhan WebSocket Constants ───────────────────────────────────────────────

#: Maximum instruments per Dhan WebSocket connection.
DHAN_MAX_INSTRUMENTS_PER_FEED: int = 1000

__all__ = [
    "DHAN_MAX_INSTRUMENTS_PER_FEED",
]
