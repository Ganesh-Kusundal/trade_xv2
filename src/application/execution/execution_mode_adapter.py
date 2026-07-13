"""Execution mode adapters for backtest/paper trading only.

DEPRECATED: Live mode now uses ExecutionEngine directly. These adapters
exist solely for backtest compatibility via OmsBacktestAdapter.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from application.execution.simulated_fill import make_simulated_submit_fn
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderResult
from domain import Order

logger = logging.getLogger(__name__)


class ExecutionModeAdapter(ABC):
    """Common interface for order execution across trading modes."""

    @abstractmethod
    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Place an order using the mode-appropriate execution path."""


class SimulatedOMSAdapter(ExecutionModeAdapter):
    """Simulated execution for paper trading and replay/backtest.

    Routes through OMS with a simulated submit_fn that generates fills
    at the current LTP. The ``order_id_prefix`` distinguishes paper
    orders ("paper-") from backtest orders ("bt-").
    """

    def __init__(self, trading_context: TradingContext, order_id_prefix: str) -> None:
        self._ctx = trading_context
        self._prefix = order_id_prefix

    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        sim_fn = submit_fn or make_simulated_submit_fn(command, order_id_prefix=self._prefix)
        return self._ctx.order_manager.place_order(command, submit_fn=sim_fn)


def create_execution_adapter(
    mode: str,
    trading_context: TradingContext,
) -> ExecutionModeAdapter:
    """Factory for execution mode adapters.

    Note: ``"live"`` mode is NOT handled here — use ExecutionEngine directly.
    """
    mode = mode.lower()
    if mode == "paper":
        return SimulatedOMSAdapter(trading_context, order_id_prefix="paper")
    if mode in ("replay", "backtest"):
        return SimulatedOMSAdapter(trading_context, order_id_prefix="bt")
    raise ValueError(
        f"Unknown execution mode: {mode}. For live mode, call OrderManager.place_order directly."
    )


