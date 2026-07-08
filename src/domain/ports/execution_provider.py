"""Execution Provider — deprecated, use protocols.ExecutionProvider instead.

This module is kept for backward compatibility.
All new code should import from ``domain.ports.protocols``.
"""

from __future__ import annotations

import warnings

from domain.ports.protocols import ExecutionProvider

warnings.warn(
    "domain.ports.execution_provider is deprecated; "
    "use 'from domain.ports.protocols import ExecutionProvider' instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["ExecutionProvider"]
