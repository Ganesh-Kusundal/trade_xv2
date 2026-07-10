"""Dhan identity — identity provider, user profile, account registry.

Re-exports key symbols from ``identity`` for backward compatibility::

    from brokers.dhan.identity import DhanIdentityProvider
"""
from brokers.dhan.identity.identity import (  # noqa: F401
    DHAN_SEGMENTS,
    DhanIdentityError,
    DhanIdentityProvider,
    DhanIdentitySource,
    DhanInstrumentRef,
    coerce_identity_provider,
    is_dhan_segment,
)
from brokers.dhan.resolver import SymbolResolver  # noqa: F401

__all__ = [
    "DHAN_SEGMENTS",
    "DhanIdentityError",
    "DhanIdentityProvider",
    "DhanIdentitySource",
    "DhanInstrumentRef",
    "SymbolResolver",
    "coerce_identity_provider",
    "is_dhan_segment",
]
