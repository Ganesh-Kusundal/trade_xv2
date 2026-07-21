"""Backward-compatibility re-export shim.

Canonical module is now ``brokers.providers.dhan._dhan_types``.
This module exists only to preserve import chains that haven't been migrated yet.
"""

from __future__ import annotations

from brokers.providers.dhan._dhan_types import *  # noqa: F403

import warnings

warnings.warn(
    "Import from brokers.providers.dhan._dhan_types instead of brokers.providers.dhan.domain",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [  # noqa: F405
    "Alert",
    "AlertRequest",
    "ConditionalTrigger",
    "ConditionalTriggerRequest",
    "DhanInstrument",
    "ExitAllResponse",
    "Exchange",
    "ForeverOrder",
    "ForeverOrderRequest",
    "IPConfig",
    "InstrumentType",
    "LedgerEntry",
    "MarginRequest",
    "MarginResponse",
    "OptionType",
    "PnlExitConfig",
    "PnlExitStatus",
    "SuperOrder",
    "SuperOrderLeg",
    "UserProfile",
]
