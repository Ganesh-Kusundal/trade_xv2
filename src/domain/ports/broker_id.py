"""BrokerId — stable enum contract for broker identification.

Canonical definition lives in :mod:`domain.enums`. This module re-exports
it so ``from domain.ports.broker_id import BrokerId`` keeps working (F7/3.4).
"""

from __future__ import annotations

from domain.enums import BrokerId

__all__ = ["BrokerId"]
