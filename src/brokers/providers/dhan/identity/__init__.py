"""Dhan identity — identity provider, user profile, account registry.

Re-exports key symbols from ``identity`` for backward compatibility::

    from brokers.providers.dhan.identity import DhanIdentityProvider
"""

from brokers.providers.dhan.identity.identity import (
    DHAN_SEGMENTS,
    DhanIdentityError,
    DhanIdentityProvider,
    DhanIdentitySource,
    DhanInstrumentRef,
    coerce_identity_provider,
    is_dhan_segment,
)
from brokers.providers.dhan.resolver import SymbolResolver

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
