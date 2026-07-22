"""Pluggable risk rules — first failure wins."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from application.risk.context import RiskCheckResult, RiskContext
from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide


class RiskRule(Protocol):
    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult: ...


class PositionLimitRule:
    def __init__(self, max_qty: Decimal) -> None:
        self._max_qty = max_qty

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        current = context.positions.get(command.instrument_id)
        current_qty = current.quantity.value if current is not None else Decimal("0")
        delta = (
            command.quantity.value
            if command.side is OrderSide.BUY
            else -command.quantity.value
        )
        projected = abs(current_qty + delta)
        if projected > self._max_qty:
            return RiskCheckResult(
                approved=False,
                reason=f"Position limit: {projected} > {self._max_qty}",
                max_quantity=self._max_qty,
            )
        return RiskCheckResult(approved=True)


class OrderSizeRule:
    def __init__(self, max_qty: Decimal) -> None:
        self._max_qty = max_qty

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        qty = command.quantity.value
        if qty > self._max_qty:
            return RiskCheckResult(
                approved=False,
                reason=f"Order size: {qty} > {self._max_qty}",
                max_quantity=self._max_qty,
            )
        return RiskCheckResult(approved=True)


class DailyLossRule:
    def __init__(self, max_loss: Decimal) -> None:
        self._max_loss = max_loss

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        if context.daily_pnl < -self._max_loss:
            return RiskCheckResult(
                approved=False,
                reason=f"Daily loss: {context.daily_pnl} < -{self._max_loss}",
            )
        return RiskCheckResult(approved=True)


class OrderRateRule:
    def __init__(self, max_orders: int) -> None:
        self._max_orders = max_orders

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        if context.order_count >= self._max_orders:
            return RiskCheckResult(
                approved=False,
                reason=f"Order rate: {context.order_count} >= {self._max_orders}",
            )
        return RiskCheckResult(approved=True)


class NotionalRule:
    """Reject order if price * quantity exceeds notional limit."""

    def __init__(self, max_notional: Decimal) -> None:
        self._max_notional = max_notional

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        notional = command.price.value * command.quantity.value
        if notional > self._max_notional:
            return RiskCheckResult(
                approved=False,
                reason=f"Notional: {notional} > {self._max_notional}",
                max_notional=self._max_notional,
            )
        return RiskCheckResult(approved=True)


class RiskRulesEngine:
    """Runs rules in order; first rejection wins."""

    def __init__(self, rules: list[RiskRule]) -> None:
        self._rules = list(rules)

    def check(self, command: PlaceOrderCommand, context: RiskContext) -> RiskCheckResult:
        for rule in self._rules:
            result = rule.check(command, context)
            if not result.approved:
                return result
        return RiskCheckResult(approved=True)
