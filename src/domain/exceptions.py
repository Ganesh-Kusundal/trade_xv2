"""Canonical exception hierarchy for the TradeXV2 platform.

This module defines the root exception and platform-level (non-broker)
exceptions. Broker transport adapters may define local exceptions that
inherit from :class:`TradeXV2Error`. Runtime resilience errors live in
``infrastructure.resilience.errors``.
"""

from __future__ import annotations


class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""


class DataError(TradeXV2Error):
    """Base exception for datalake and data processing errors."""


class ConfigError(TradeXV2Error):
    """Configuration error (missing or invalid settings)."""


class ValidationError(TradeXV2Error):
    """Input validation error."""


__all__ = [
    "ConfigError",
    "DataError",
    "TradeXV2Error",
    "ValidationError",
]
