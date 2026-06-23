"""Shim — import from :mod:`domain.exchange_segments` instead (deprecated)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.exchange_segments instead of brokers.common.core.exchange_segments (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.exchange_segments import *  # noqa: F403, E402
