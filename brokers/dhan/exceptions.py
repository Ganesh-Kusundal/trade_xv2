"""Dhan broker exceptions.

All Dhan-specific exceptions extend from the canonical ``BrokerError``
hierarchy in ``brokers.common.resilience.errors``. The only exception
class defined here that also exists in common is ``RateLimitError`` —
we alias it to the canonical one to avoid the silent-bug risk of
catching the wrong class.

Usage::

    from brokers.dhan.exceptions import OrderError, InstrumentNotFoundError
    from brokers.common.resilience.errors import RateLimitError  # canonical
"""

from __future__ import annotations

from brokers.common.resilience.errors import BrokerError, RateLimitError

# Re-export canonical RateLimitError so existing imports still work.
# New code should import directly from brokers.common.resilience.errors.
__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "ConditionalTriggerError",
    "DhanError",
    "DhanIdentityError",
    "EDISError",
    "ExitAllError",
    "ForeverOrderError",
    "InstrumentNotFoundError",
    "IPManagementError",
    "LedgerError",
    "MarketDataError",
    "OrderError",
    "RateLimitError",  # alias to canonical
    "SuperOrderError",
    "UserProfileError",
]


class DhanError(BrokerError):
    """Base exception for all Dhan broker errors.

    Extends the canonical ``BrokerError`` so that catching ``BrokerError``
    catches exceptions from any broker adapter.
    """


class InstrumentNotFoundError(DhanError):
    """Instrument not found in resolver cache."""


class MarketDataError(DhanError):
    """Market data fetch failure."""


class OrderError(DhanError):
    """Order placement/modification/cancellation failure."""


class AuthenticationError(DhanError):
    """Token expired or rejected."""


class ConfigurationError(DhanError):
    """Missing or invalid configuration."""


class DhanIdentityError(DhanError):
    """Non-Dhan identifier leaked into a Dhan payload or identity validation failure."""


# ── Feature-specific exceptions ──────────────────────────────────────────


class SuperOrderError(DhanError):
    """Super order placement/modification/cancellation failure."""


class ForeverOrderError(DhanError):
    """Forever order placement/modification/cancellation failure."""


class ConditionalTriggerError(DhanError):
    """Conditional trigger creation/modification/deletion failure."""


class LedgerError(DhanError):
    """Ledger fetch failure."""


class UserProfileError(DhanError):
    """User profile fetch failure."""


class IPManagementError(DhanError):
    """IP management operation failure."""


class ExitAllError(DhanError):
    """Exit all operation failure."""


class EDISError(DhanError):
    """eDIS/TPIN operation failure."""
