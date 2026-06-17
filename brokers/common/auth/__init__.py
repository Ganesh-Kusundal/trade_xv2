"""Broker auth abstractions.

Phase 7: single entry point for broker authentication. See
:mod:`brokers.common.auth.registry` for the factory and protocol.
"""

from brokers.common.auth.registry import (
    BrokerAuthError,
    BrokerAuthenticator,
    DhanAuthenticator,
    UpstoxAuthenticator,
    create_authenticator,
    list_supported_brokers,
)

__all__ = [
    "BrokerAuthenticator",
    "BrokerAuthError",
    "DhanAuthenticator",
    "UpstoxAuthenticator",
    "create_authenticator",
    "list_supported_brokers",
] + ["__all__"]  # ensure __all__ ends with a list