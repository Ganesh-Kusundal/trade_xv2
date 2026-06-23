"""Shim — import from :mod:`domain.reconciliation` instead (deprecated)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.reconciliation instead of brokers.common.core.reconciliation (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.reconciliation import *  # noqa: F403, E402
