"""Dhan WebSocket tuning constants — single source of truth.

These were previously scattered as ``os.getenv`` reads across
``domain/constants/ws.py`` and several broker modules. They now live in
one config-owned module so defaults, overrides, and validation have a single
point of control. ``domain`` must not read env directly (layering contract),
so the values are owned here and imported by the broker layer.
"""

from __future__ import annotations

import os

#: Maximum reconnection attempts for Dhan WebSocket before entering cooldown.
DHAN_MAX_RECONNECT_ATTEMPTS: int = int(os.getenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50"))

#: Staleness threshold in seconds for detecting stale Dhan WebSocket connections.
DHAN_STALENESS_THRESHOLD_SECONDS: float = float(
    os.getenv("DHAN_STALENESS_THRESHOLD_SECONDS", "60.0")
)

#: Cooldown period in seconds after max reconnect attempts exceeded.
DHAN_RECONNECT_COOLDOWN_SECONDS: float = float(os.getenv("DHAN_RECONNECT_COOLDOWN_SECONDS", "300"))

__all__ = [
    "DHAN_MAX_RECONNECT_ATTEMPTS",
    "DHAN_RECONNECT_COOLDOWN_SECONDS",
    "DHAN_STALENESS_THRESHOLD_SECONDS",
]
