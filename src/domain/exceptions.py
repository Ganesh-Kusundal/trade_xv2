"""Canonical exception hierarchy for the TradeXV2 platform.

This module defines the root exception and platform-level (non-broker)
exceptions. Broker transport adapters may define local exceptions that
inherit from :class:`TradeXV2Error`. Runtime resilience errors live in
``infrastructure.resilience.errors``.
"""

from __future__ import annotations


class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""


class ServiceNotFoundError(TradeXV2Error):
    """Raised when resolving a service that is not registered."""


class DataError(TradeXV2Error):
    """Base exception for datalake and data processing errors."""


class ExchangeNotConfigured(DataError):
    """Raised when datalake/data code needs an exchange but none is active.

    ADR-005: replaces the previous silent ``exchange="NSE"`` default. Callers
    must register an exchange plugin (``tradex.exchanges``) before performing
    exchange-specific operations.
    """


class ConfigError(TradeXV2Error):
    """Configuration error (missing or invalid settings)."""


class ValidationError(TradeXV2Error):
    """Input validation error."""


class LiveBrokerBlockedError(TradeXV2Error, RuntimeError):
    """Raised when a live broker order is blocked by the readiness gate.

    Both order spines (Spine A: BrokerSession → ExecutionManager, Spine B:
    MCP tools → orders.py) raise this when the production readiness gate
    refuses a live broker.  Callers should catch ``TradeXV2Error`` or
    ``LiveBrokerBlockedError`` specifically — never fall through to a
    generic ``except Exception``.

    .. note::
        Also inherits ``RuntimeError`` for backward compatibility with
        existing ``except RuntimeError`` blocks on order paths.
    """


__all__ = [
    "ConfigError",
    "DataError",
    "ExchangeNotConfigured",
    "LiveBrokerBlockedError",
    "ServiceNotFoundError",
    "TradeXV2Error",
    "ValidationError",
]
