"""FundAllocator — Capital pool allocator, pre-trade margin check, and order slicer.

Manages strategy capital boundaries, pre-trade margin gates, and automatic
order slicing for exchange quantity freeze limits (e.g. 1,800 contracts for NSE NIFTY options).
"""

from __future__ import annotations

import math
from decimal import Decimal
import threading
from domain.exceptions import TradeXV2Error


class InsufficientCapitalError(TradeXV2Error):
    """Raised when strategy margin reservation exceeds allocated pool capital."""


class SliceManager:
    """Automatic order quantity slicer for exchange freeze limits."""

    def __init__(self, max_freeze_quantity: int = 1800) -> None:
        self.max_freeze_quantity = max_freeze_quantity

    def slice_quantity(self, quantity: int) -> list[int]:
        """Slice order quantity into chunks not exceeding max_freeze_quantity."""
        if quantity <= 0:
            return []
        if quantity <= self.max_freeze_quantity:
            return [quantity]

        slices = []
        remaining = quantity
        while remaining > 0:
            chunk = min(remaining, self.max_freeze_quantity)
            slices.append(chunk)
            remaining -= chunk

        return slices


class FundAllocator:
    """Manages dedicated capital pools and pre-trade margin reservations per strategy."""

    def __init__(self, total_capital: Decimal) -> None:
        self._total_capital = total_capital
        self._strategy_allocated: dict[str, Decimal] = {}
        self._strategy_reserved: dict[str, Decimal] = {}
        self._lock = threading.Lock()

    def allocate_strategy_pool(self, strategy_name: str, capital: Decimal) -> None:
        with self._lock:
            self._strategy_allocated[strategy_name] = capital
            if strategy_name not in self._strategy_reserved:
                self._strategy_reserved[strategy_name] = Decimal("0")

    def get_available_capital(self, strategy_name: str) -> Decimal:
        with self._lock:
            allocated = self._strategy_allocated.get(strategy_name, Decimal("0"))
            reserved = self._strategy_reserved.get(strategy_name, Decimal("0"))
            return max(Decimal("0"), allocated - reserved)

    def reserve_margin(self, strategy_name: str, margin_required: Decimal) -> bool:
        with self._lock:
            available = self.get_available_capital(strategy_name)
            if margin_required > available:
                raise InsufficientCapitalError(
                    f"Strategy '{strategy_name}' requires margin {margin_required} but only {available} available"
                )
            
            self._strategy_reserved[strategy_name] = (
                self._strategy_reserved.get(strategy_name, Decimal("0")) + margin_required
            )
            return True

    def release_margin(self, strategy_name: str, margin_released: Decimal) -> None:
        with self._lock:
            current_reserved = self._strategy_reserved.get(strategy_name, Decimal("0"))
            self._strategy_reserved[strategy_name] = max(Decimal("0"), current_reserved - margin_released)
