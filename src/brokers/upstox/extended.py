"""Deprecated alias — use brokers.upstox.extras.

ADR: upstox extras (IPO/news/fundamentals) are intentionally non-parity with
dhan extended.py (derivatives). Callers should import from extras.
"""
from __future__ import annotations
from brokers.upstox.extras import UpstoxExtendedCapabilities  # noqa: F401
