"""Risk Engine module -- pre-trade risk checks.

Provides configurable risk limits that are evaluated before an order is
sent to the broker, preventing oversized positions or orders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import List

from brokers.common.core.domain import Position, Side

# -- Risk Check Result -------------------------------------------------------


@dataclass
class RiskCheckResult:
    """Outcome of a pre-trade risk check."""

    passed: bool
    reason: str = ""


# -- Risk Engine ABC & Implementation ----------------------------------------


class RiskEngine(ABC):
    """Abstract risk engine interface."""

    @abstractmethod
    def check_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        positions: list[Position],
    ) -> RiskCheckResult:
        """Evaluate whether an order passes risk limits."""
        ...


class SimpleRiskEngine(RiskEngine):
    """Risk engine with configurable position-value and order-value limits.

    Parameters
    ----------
    max_position_value:
        Maximum allowed notional value for any single position after
        the proposed order.  Defaults to 1,000,000.
    max_order_value:
        Maximum allowed notional value for a single order.
        Defaults to 500,000.
    """

    def __init__(
        self,
        max_position_value: Decimal = Decimal("1000000"),
        max_order_value: Decimal = Decimal("500000"),
    ) -> None:
        self.max_position_value = max_position_value
        self.max_order_value = max_order_value

    def check_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        positions: list[Position],
    ) -> RiskCheckResult:
        order_value = Decimal(str(quantity)) * price

        # -- Check single-order value limit ----------------------------------
        if order_value > self.max_order_value:
            return RiskCheckResult(
                passed=False,
                reason=(
                    f"Order value {order_value} exceeds max order value {self.max_order_value}"
                ),
            )

        # -- Check post-trade position value limit ---------------------------
        existing_qty = 0
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                existing_qty += pos.quantity

        projected_qty = existing_qty + quantity if side == Side.BUY else existing_qty - quantity

        projected_value = abs(Decimal(str(projected_qty)) * price)
        if projected_value > self.max_position_value:
            return RiskCheckResult(
                passed=False,
                reason=(
                    f"Projected position value {projected_value} exceeds "
                    f"max position value {self.max_position_value}"
                ),
            )

        return RiskCheckResult(passed=True)
