"""Ordered risk policy chain for RiskManager.check_order (CODE-001)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.oms._internal.risk_types import RiskResult
    from domain.entities.order import Order


PolicyFn = Callable[["Order", "RiskPolicyContext"], "RiskResult | None"]


class RiskPolicyContext:
    """Shared read-only context passed through the policy chain."""

    __slots__ = ("manager",)

    def __init__(self, manager) -> None:
        self.manager = manager


def run_policy_chain(
    order: Order,
    ctx: RiskPolicyContext,
    policies: list[PolicyFn],
) -> RiskResult | None:
    """Run policies in order; return first denial or None if all pass."""
    for policy in policies:
        result = policy(order, ctx)
        if result is not None and not result.allowed:
            return result
    return None


__all__ = ["PolicyFn", "RiskPolicyContext", "run_policy_chain"]
