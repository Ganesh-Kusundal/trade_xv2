"""Brokers exceptions — broker-access exception hierarchy.

Reuses the canonical domain error types and adds broker-scoped wrappers only
where the domain layer does not already cover the case.
"""

from __future__ import annotations

from domain.connect_errors import ConnectError
from domain.errors import BrokerError, NotConfiguredError
from domain.exceptions import *  # noqa: F401,F403  (re-export domain exceptions)
from domain.exceptions import __all__ as _domain_exc_all


class BrokerNotAvailable(BrokerError):
    """Raised when a requested broker plugin is not registered/available."""


class CapabilityNotSupported(BrokerError):
    """Raised when an instrument/broker lacks a requested capability."""


__all__ = list(_domain_exc_all) + [
    "BrokerError",
    "BrokerNotAvailable",
    "CapabilityNotSupported",
    "ConnectError",
    "NotConfiguredError",
]