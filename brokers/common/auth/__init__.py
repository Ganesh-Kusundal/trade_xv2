"""Broker auth abstractions.

Phase 7: single entry point for broker authentication. See
:mod:`brokers.common.auth.registry` for the factory and protocol.

Concrete authenticator implementations are in broker-specific modules:
- DhanAuthenticator: brokers.dhan.auth
- UpstoxAuthenticator: brokers.upstox.auth.authenticator
"""

from brokers.common.auth.registry import (
    BrokerAuthError,
    BrokerAuthenticator,
    create_authenticator,
    list_supported_brokers,
)
from brokers.common.auth.credential_resolver import (
    CANONICAL_ENV_FILES,
    CredentialResolver,
)
from brokers.common.auth.credential_validator import (
    CredentialIssue,
    CredentialValidator,
)
from brokers.common.auth.token import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
    TotpGenerator,
)
from brokers.common.auth.environment_bootstrap import bootstrap_environment
from brokers.common.auth.jwt_expiry import JwtExpiry
from brokers.common.auth.token_policy import should_generate_token

__all__ = [
    "AuthManager",
    "BrokerAuthenticator",
    "BrokerAuthError",
    "CANONICAL_ENV_FILES",
    "CredentialIssue",
    "CredentialResolver",
    "CredentialValidator",
    "EnvTokenStateStore",
    "bootstrap_environment",
    "JsonTokenStateStore",
    "JwtExpiry",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "TotpGenerator",
    "create_authenticator",
    "list_supported_brokers",
    "should_generate_token",
]
