"""Backward-compatibility re-export shim.

Canonical package is now ``brokers.providers.dhan.market_data``.
This package exists only to preserve import chains that haven't been migrated yet.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "Import from brokers.providers.dhan.market_data instead of brokers.providers.dhan.data",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
