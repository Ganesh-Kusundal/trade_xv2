"""Broker auth errors shared across broker implementations."""

from __future__ import annotations


class BrokerAuthError(RuntimeError):
    """Raised when broker authentication fails and cannot be recovered."""
