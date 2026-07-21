"""Backward-compatibility re-export shim.

Canonical module is now ``brokers.providers.dhan.data_capabilities``.
"""

from __future__ import annotations

import warnings

from brokers.providers.dhan.data_capabilities import DhanDataCapabilities  # noqa: F401

warnings.warn(
    "Import from brokers.providers.dhan.data_capabilities instead of brokers.providers.dhan.extended_data",
    DeprecationWarning,
    stacklevel=2,
)
