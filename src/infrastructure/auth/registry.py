"""Broker auth errors shared across broker implementations."""

from __future__ import annotations

from __future__ import annotations

from domain.errors import TradeXV2Error


class BrokerAuthError(TradeXV2Error):
    """Raised when broker authentication fails and cannot be recovered."""


def list_supported_brokers() -> frozenset[str]:
    """Return the set of broker IDs that have authenticator implementations."""
    return frozenset({"dhan", "upstox"})
