"""Canonical domain — public re-export facade (shim to :mod:`domain`)."""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "Import from domain.* instead of brokers.common.core.domain (shim deprecated). "
    "See docs/REFACTORING_PLAYBOOK.md for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from domain import *  # noqa: F403, E402
