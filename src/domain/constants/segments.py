"""Exchange segment set helpers — single source of truth for segment grouping.

Extracted from scattered duplicates in broker extensions:
- `brokers.upstox.extensions.depth._NSE_SEGMENTS`
- `brokers.dhan.extensions.depth20._NSE_SEGMENTS`
- `brokers.dhan.extensions.depth200._NSE_SEGMENTS`

All broker extensions should use `nse_eligible_segments()` instead of
defining their own duplicated frozensets.
"""

from __future__ import annotations

from domain.constants.exchanges import (
    NFO,
    NSE,
    WIRE_IDX,
    WIRE_NSE_EQ,
    WIRE_NSE_FNO,
)

# ── NSE-eligible segments (for depth extensions) ─────────────────────────────

NSE_ELIGIBLE_SEGMENTS: frozenset[str] = frozenset({NSE, WIRE_NSE_EQ, NFO, WIRE_NSE_FNO, WIRE_IDX})


def nse_eligible_segments() -> frozenset[str]:
    """Return the set of segments that support NSE-based depth extensions.

    Used by DepthExtension implementations to check `instrument.exchange in segments`.
    """
    return NSE_ELIGIBLE_SEGMENTS


def is_nse_eligible(exchange: str) -> bool:
    """Check if an exchange code supports NSE-based features (depth, gtt, etc.)."""
    return exchange in NSE_ELIGIBLE_SEGMENTS


__all__ = [
    "NSE_ELIGIBLE_SEGMENTS",
    "is_nse_eligible",
    "nse_eligible_segments",
]
