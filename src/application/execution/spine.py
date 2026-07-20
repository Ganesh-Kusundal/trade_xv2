"""Single OMS placement spine — all execution targets converge here.

Constitution P1: one path from approved Order intent to OrderManager + ExecutionTarget.
"""

from __future__ import annotations

from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain.ports.execution_target import ExecutionTarget


def place_order_spine(
    order_manager: OrderManager,
    command: OmsOrderCommand,
    target: ExecutionTarget,
) -> OrderResult:
    """Place an order through OMS using the resolved execution target."""
    return order_manager.place_order(command, submit_fn=target.submit_fn())


__all__ = ["place_order_spine"]
