"""Brokers that place orders against live exchange capital (not paper/sim)."""

from __future__ import annotations

# Canonical set — import here so application/oms never embeds broker name literals.
LIVE_CAPITAL_BROKER_IDS: frozenset[str] = frozenset({"dhan", "upstox"})
