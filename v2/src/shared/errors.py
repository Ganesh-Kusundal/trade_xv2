"""Shared error hierarchy for TradeX V2."""

from __future__ import annotations


class TradexError(Exception):
    """Base error for all TradeX framework failures."""


class LifecycleError(TradexError):
    """Invalid component lifecycle transition or startup abort."""


class BrokerError(TradexError):
    """Canonical broker-transport failure — catch this, not raw HTTP/network errors."""


class AuthenticationError(BrokerError):
    """401/403 — token rejected or forbidden."""


class RateLimitError(BrokerError):
    """429 or local rate-limit-bucket exhaustion."""


class NetworkError(BrokerError):
    """5xx, retry exhaustion, or circuit-breaker open — transient/unreachable."""


class MappingError(BrokerError):
    """Native broker ID has no canonical InstrumentId — never fabricate one, raise instead."""
