"""Shared error hierarchy for TradeX V2."""

from __future__ import annotations


class TradexError(Exception):
    """Base error for all TradeX framework failures."""


class LifecycleError(TradexError):
    """Invalid component lifecycle transition or startup abort."""
