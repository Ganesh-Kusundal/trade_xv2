"""Deprecated re-export — use ``brokers.dhan.transport.DhanOrderTransport``.

ENG-016: residual ``providers/`` package folds into broker transports.
"""

from __future__ import annotations

import warnings

from brokers.dhan.transport import DhanOrderTransport as DhanExecutionProvider

warnings.warn(
    "providers.dhan.execution_provider is deprecated; use "
    "brokers.dhan.transport.DhanOrderTransport (ENG-016).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DhanExecutionProvider"]
