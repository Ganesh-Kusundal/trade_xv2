"""FillSource protocol — the only mode-specific piece of execution.

Live uses BrokerFillSource (delegates to broker gateway).
Paper/backtest uses SimulatedFillSource (generates simulated fills).
Both satisfy the same protocol so ExecutionEngine is mode-agnostic.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from application.oms.order_manager import OmsOrderCommand
from domain import Order


@runtime_checkable
class FillSource(Protocol):
    """Protocol for order submission — the mode-specific seam."""

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        """Return a submit_fn suitable for OrderManager.place_order."""
        ...


class BrokerFillSource:
    """Live fill source — delegates to broker gateway."""

    def __init__(self, gateway) -> None:
        self._gateway = gateway

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        from application.execution.gateway_submit import make_gateway_submit_fn
        return make_gateway_submit_fn(self._gateway)


class SimulatedFillSource:
    """Paper/backtest fill source — fills synchronously at LTP."""

    def __init__(self, order_id_prefix: str = "sim") -> None:
        self._prefix = order_id_prefix

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        from application.execution.simulated_fill import make_simulated_submit_fn
        prefix = self._prefix

        def _submit(command: OmsOrderCommand) -> Order:
            fn = make_simulated_submit_fn(command, order_id_prefix=prefix)
            return fn(command)

        return _submit
