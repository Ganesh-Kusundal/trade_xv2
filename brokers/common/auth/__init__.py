"""Broker auth abstractions.

Phase 7: single entry point for broker authentication. See
:mod:`brokers.common.auth.registry` for the factory and protocol.

Concrete authenticator implementations are in broker-specific modules:
- DhanAuthenticator: brokers.dhan.auth
- UpstoxAuthenticator: brokers.upstox.auth
"""

from brokers.common.auth.registry import (
    BrokerAuthError,
    BrokerAuthenticator,
    create_authenticator,
    list_supported_brokers,
)

__all__ = [
    "BrokerAuthenticator",
    "BrokerAuthError",
    "create_authenticator",
    "list_supported_brokers",
]
