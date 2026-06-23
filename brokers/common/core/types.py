"""Shim — import from :mod:`domain.types` instead (deprecated)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.types instead of brokers.common.core.types (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.types import *  # noqa: F403, E402
