"""RiskModel protocol — pre-trade and position risk checks."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from domain.commands import PlaceOrderCommand
from domain.entities import Account, Position
from domain.ports.types import RiskContext

# Return type is `Any`, not application.risk.context.RiskCheckResult: domain may
# not import application (import-linter "Domain has no outer imports" contract).


@runtime_checkable
class RiskModel(Protocol):
    def check_order(
        self, command: PlaceOrderCommand, context: RiskContext
    ) -> Any: ...
    def check_position(
        self, position: Position, context: RiskContext
    ) -> Any: ...
    def check_account(
        self, account: Account, context: RiskContext
    ) -> Any: ...
