"""FillSource protocol — implements domain ExecutionTarget.

Live uses BrokerFillSource (delegates to broker gateway).
Paper uses PaperFillSource (market-data LTP pricing).
Backtest/replay uses SimulatedFillSource (deterministic sim fills).
All satisfy ExecutionTarget so ExecutionEngine is mode-agnostic.

Constitution alias: ExecutionTarget (``domain.ports.execution_target``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Protocol, runtime_checkable

from application.oms.order_manager import OmsOrderCommand
from domain import Order
from domain.ports.execution_target import ExecutionTargetKind


@runtime_checkable
class FillSource(Protocol):
    """Protocol for order submission — implements ExecutionTarget seam."""

    @property
    def kind(self) -> ExecutionTargetKind: ...

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

    def cancel_fn(self) -> Callable[[str], bool] | None:
        from application.execution.gateway_cancel_modify import make_gateway_cancel_fn

        if getattr(self._gateway, "cancel_order", None) is None:
            return None
        return make_gateway_cancel_fn(self._gateway)

    def modify_fn(self) -> Callable | None:
        from application.execution.gateway_cancel_modify import make_gateway_modify_fn

        if getattr(self._gateway, "modify_order", None) is None:
            return None
        return make_gateway_modify_fn(self._gateway)

    def capabilities(self) -> object | None:
        from application.execution.gateway_cancel_modify import gateway_capabilities

        return gateway_capabilities(self._gateway)


class PaperFillSource:
    """Paper execution target — prices from market-data, records via OMS spine."""

    def __init__(
        self,
        quote_fn: Callable[[str, str], Decimal] | None = None,
        *,
        order_id_prefix: str = "paper",
        kind: ExecutionTargetKind = ExecutionTargetKind.PAPER,
    ) -> None:
        self._quote_fn = quote_fn
        self._prefix = order_id_prefix
        self._kind = kind

    @property
    def kind(self) -> ExecutionTargetKind:
        return self._kind

    def submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        from application.execution.simulated_fill import make_simulated_submit_fn

        quote_fn = self._quote_fn
        prefix = self._prefix

        def _submit(command: OmsOrderCommand) -> Order:
            cmd = command
            if quote_fn is not None:
                ltp = quote_fn(command.symbol, command.exchange)
                if ltp and ltp > 0:
                    cmd = replace(command, price=ltp)
            fn = make_simulated_submit_fn(cmd, order_id_prefix=prefix)
            return fn(cmd)

        return _submit


class SimulatedFillSource:
    """Backtest/replay fill source — deterministic synchronous fills."""

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
