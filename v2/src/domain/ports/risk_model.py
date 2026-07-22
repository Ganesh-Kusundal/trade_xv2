"""RiskModel protocol — pre-trade and position risk checks."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Position
from domain.messages import RiskCheckResult
from domain.ports.types import RiskContext


@runtime_checkable
class RiskModel(Protocol):
    def check_order(
        self, command: PlaceOrderCommand, context: RiskContext
    ) -> RiskCheckResult: ...
    def check_position(
        self, position: Position, context: RiskContext
    ) -> RiskCheckResult: ...
    def check_account(
        self, account: Account, context: RiskContext
    ) -> RiskCheckResult: ...
