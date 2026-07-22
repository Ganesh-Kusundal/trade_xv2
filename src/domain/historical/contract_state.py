"""Contract lifecycle state for historical routing."""

from __future__ import annotations

from enum import Enum


class ContractState(str, Enum):
    """Whether a derivative contract is currently tradable or expired."""

    ACTIVE = "active"
    EXPIRED = "expired"
    AUTO = "auto"  # resolve via instrument master / expiry date vs today
