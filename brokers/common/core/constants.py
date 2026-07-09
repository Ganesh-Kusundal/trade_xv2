"""Broker-side re-export shim for core constants.

The canonical constant definitions live in ``src/domain/constants`` (the
single source of truth for all domain constants). This module re-exports
them so existing ``from brokers.common.core.constants import ...`` imports
resolve without duplicating any values into the broker layer.

This is a FIX-ONLY shim — no constants are redefined here.
"""

from __future__ import annotations

from src.domain.constants import *  # noqa: F401,F403
from src.domain.constants import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    DEFAULT_TICK_SIZE,
    OBSERVABILITY_DEFAULT_HOST,
    OBSERVABILITY_DEFAULT_PORT,
    PHANTOM_CAPITAL_INR,
    RECONCILIATION_INTERVAL_SECONDS,
    TOKEN_CLOCK_SKEW_SECONDS,
)

__all__ = [
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_TICK_SIZE",
    "OBSERVABILITY_DEFAULT_HOST",
    "OBSERVABILITY_DEFAULT_PORT",
    "PHANTOM_CAPITAL_INR",
    "RECONCILIATION_INTERVAL_SECONDS",
    "TOKEN_CLOCK_SKEW_SECONDS",
]
