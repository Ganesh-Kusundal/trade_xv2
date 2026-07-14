"""Canonical Indian exchange trading-session hours (IST).

Single source of truth for the regular-market session timings used across
the codebase. Previously the same ``time(9, 15)`` / ``time(15, 30)`` pair
was duplicated in three independent modules; any change (e.g. a new
muhurat session or an early-close convention) had to be applied in every
copy. Centralizing here means one edit propagates everywhere.

All times are IST-naive ``datetime.time`` values — callers that need a
timezone-aware instant must combine them with :data:`domain.constants.IST`.
"""

from __future__ import annotations

from datetime import time

# NSE/BSE equity + F&O regular continuous trading session (IST, naive).
NSE_EQUITY_OPEN: time = time(9, 15)
NSE_EQUITY_CLOSE: time = time(15, 30)
