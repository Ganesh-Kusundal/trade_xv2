"""Data Provider — deprecated, use protocols.DataProvider instead.

This module is kept for backward compatibility.
All new code should import from ``domain.ports.protocols``.
"""

from __future__ import annotations

import warnings

from domain.ports.protocols import DataProvider

warnings.warn(
    "domain.ports.data_provider is deprecated; "
    "use 'from domain.ports.protocols import DataProvider' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DataProvider"]
