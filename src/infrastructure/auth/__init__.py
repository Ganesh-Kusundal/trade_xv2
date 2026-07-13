"""Canonical auth — credential resolution, token lifecycle, auth bootstrapping."""
from infrastructure.auth.credential_resolver import CredentialResolver
from infrastructure.auth.credential_validator import CredentialIssue, CredentialValidator
from infrastructure.auth.environment_bootstrap import bootstrap_environment
from infrastructure.auth.jwt_expiry import JwtExpiry
from infrastructure.auth.metrics import AuthMetrics
from infrastructure.auth.registry import BrokerAuthError
from infrastructure.auth.token import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
)
from infrastructure.auth.token_ensure import ensure_access_token
from infrastructure.auth.token_policy import should_generate_token

__all__ = [
    "AuthManager",
    "AuthMetrics",
    "BrokerAuthError",
    "CredentialIssue",
    "CredentialResolver",
    "CredentialValidator",
    "EnvTokenStateStore",
    "JsonTokenStateStore",
    "JwtExpiry",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "bootstrap_environment",
    "ensure_access_token",
    "should_generate_token",
]
