"""Backward-compat shim — ``BrokerFactory`` now lives in ``brokers.dhan.identity.factory``."""
from brokers.dhan.auth.token_scheduler import TokenRefreshScheduler  # noqa: F401
from brokers.dhan.identity.factory import (  # noqa: F401
    BrokerFactory,
    _generate_totp_token,
    _next_token_expiry,
    _refresh_via_auth,
    _update_env_token,
)

__all__ = [
    "BrokerFactory",
    "TokenRefreshScheduler",
    "_generate_totp_token",
    "_next_token_expiry",
    "_refresh_via_auth",
    "_update_env_token",
]
