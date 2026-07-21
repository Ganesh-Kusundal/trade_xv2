"""Backward-compatibility re-export shim.

Canonical module is now ``brokers.providers.dhan.account_capabilities``.
"""

from __future__ import annotations

import warnings

from brokers.providers.dhan.account_capabilities import DhanAccountCapabilities  # noqa: F401

warnings.warn(
    "Import from brokers.providers.dhan.account_capabilities instead of brokers.providers.dhan.extended_account",
    DeprecationWarning,
    stacklevel=2,
)
