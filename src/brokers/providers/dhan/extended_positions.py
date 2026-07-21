"""Backward-compatibility re-export shim.

Canonical module is now ``brokers.providers.dhan.position_capabilities``.
"""

from __future__ import annotations

import warnings

from brokers.providers.dhan.position_capabilities import DhanPositionCapabilities  # noqa: F401

warnings.warn(
    "Import from brokers.providers.dhan.position_capabilities instead of brokers.providers.dhan.extended_positions",
    DeprecationWarning,
    stacklevel=2,
)
