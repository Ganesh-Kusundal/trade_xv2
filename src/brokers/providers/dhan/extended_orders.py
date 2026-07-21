"""Backward-compatibility re-export shim.

Canonical module is now ``brokers.providers.dhan.order_capabilities``.
"""

from __future__ import annotations

import warnings

from brokers.providers.dhan.order_capabilities import DhanOrderCapabilities  # noqa: F401

warnings.warn(
    "Import from brokers.providers.dhan.order_capabilities instead of brokers.providers.dhan.extended_orders",
    DeprecationWarning,
    stacklevel=2,
)
