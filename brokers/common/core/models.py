"""Shim — import from :mod:`domain.entities` instead (deprecated)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.entities instead of brokers.common.core.models (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.entities import *  # noqa: F403, E402
