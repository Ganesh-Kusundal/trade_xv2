"""Subscription Handle — deprecated, use protocols.SubscriptionHandle instead.

This module is kept for backward compatibility.
All new code should import from ``domain.ports.protocols``.
"""

from __future__ import annotations

import warnings

from domain.ports.protocols import SubscriptionHandle

warnings.warn(
    "domain.ports.subscription_handle is deprecated; "
    "use 'from domain.ports.protocols import SubscriptionHandle' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["SubscriptionHandle"]
