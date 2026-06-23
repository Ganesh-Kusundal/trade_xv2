"""Shim — import from :mod:`domain.field_mapping` instead (deprecated)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.field_mapping instead of brokers.common.core.field_mapping (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain.field_mapping import *  # noqa: F403, E402
