"""FillSource protocol — implements domain ExecutionTarget.

Live uses BrokerFillSource (delegates to broker gateway).
Paper/backtest/replay uses SimulatedFillSource (generates simulated fills).
Both satisfy ExecutionTarget so ExecutionEngine is mode-agnostic.

Constitution alias: ExecutionTarget (``domain.ports.execution_target``).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from domain.ports.execution_target import ExecutionTarget, ExecutionTargetKind
from application.oms.order_manager import OmsOrderCommand
from domain import Order


@runtime_checkable
class FillSource(Protocol):
    """Protocol for order submission — implements ExecutionTarget seam."""

    @property
    def kind(self) -> ExecutionTargetKind:
        ...

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        """Return a submit_fn suitable for OrderManager.place_order."""
        ...


class BrokerFillSource:
    """Live fill source — delegates to broker gateway."""

    def __init__(
        self,
        gateway,
        *,
        kind: ExecutionTargetKind = ExecutionTargetKind.LIVE,
    ) -> None:
        self._gateway = gateway
        self._kind = kind

    @property
    def kind(self) -> ExecutionTargetKind:
        return self._kind

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        from application.execution.gateway_submit import make_gateway_submit_fn
        return make_gateway_submit_fn(self._gateway)


class SimulatedFillSource:
    """Paper/backtest/replay fill source — fills synchronously at LTP."""

    def __init__(
        self,
        order_id_prefix: str = "sim",
        *,
        kind: ExecutionTargetKind = ExecutionTargetKind.PAPER,
    ) -> None:
        self._prefix = order_id_prefix
        self._kind = kind

    @property
    def kind(self) -> ExecutionTargetKind:
        return self._kind

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        from application.execution.simulated_fill import make_simulated_submit_fn
        prefix = self._prefix

        def _submit(command: OmsOrderCommand) -> Order:
            fn = make_simulated_submit_fn(command, order_id_prefix=prefix)
            return fn(command)

        return _submit


class CallableExecutionTarget:
    """Wrap a submit_fn as an ExecutionTarget (composer quota path, paper fills)."""

    def __init__(
        self,
        submit_fn: Callable[[OmsOrderCommand], Order],
        *,
        kind: ExecutionTargetKind = ExecutionTargetKind.LIVE,
    ) -> None:
        self._submit_fn = submit_fn
        self._kind = kind

    @property
    def kind(self) -> ExecutionTargetKind:
        return self._kind

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        return self._submit_fn
