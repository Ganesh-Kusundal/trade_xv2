"""Shim — import from :mod:`domain.result` instead (deprecated)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.result instead of brokers.common.core.result (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.result import *  # noqa: F403, E402
