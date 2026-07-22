"""RiskModel port — pre-trade risk check interface."""

from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskCheckResult:
    approved: bool
    reason: str = ""


@dataclass(frozen=True)
class RiskContext:
    account: object
    positions: dict
    open_orders: list


@runtime_checkable
class RiskModel(Protocol):
    def check_order(self, command: object, context: RiskContext) -> RiskCheckResult: ...
