"""BrokerId — stable enum contract for broker identification.

G1 (P5-1): replaces string-based broker selection with an enum.
This is the single source of truth for broker identifiers. All
string comparisons against broker names should use this enum instead.
"""

from __future__ import annotations

from enum import Enum


class BrokerId(str, Enum):
    """Canonical broker identifiers.

    Used by:
    - Runtime composition root (broker selection)
    - BrokerService (active broker tracking)
    - Interface layer (diagnostic tools, doctor commands)
    - Tests (broker-specific fixtures)
    """

    DHAN = "dhan"
    UPSTOX = "upstox"
    PAPER = "paper"
    MOCK = "mock"

    @classmethod
    def from_str(cls, value: str) -> BrokerId:
        """Convert a string to BrokerId (case-insensitive).

        Raises ValueError for unknown broker names.
        """
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(
                f"Unknown broker '{value}'. "
                f"Valid broker IDs: {[b.value for b in cls]}"
            ) from None


__all__ = ["BrokerId"]
