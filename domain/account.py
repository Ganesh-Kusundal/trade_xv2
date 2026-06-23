"""Canonical account balance dataclass.

Submodule of :mod:`domain.entities` — imported via the re-export facade.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class Balance:
    """Canonical account balance — returned by every broker adapter.

    Consolidated with the former ``FundLimits`` class (REF-024).
    """

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    utilized_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")

    def has_sufficient(self, required: Decimal) -> bool:
        """Return True if available balance covers the required amount."""
        return self.available_balance >= required


# Backward-compatible alias — REF-024 consolidated FundLimits into Balance.
# New code should use ``Balance``; ``FundLimits`` remains for existing callers.
FundLimits = Balance
