"""Execution mode adapters — unify paper and replay fill paths through OMS.

Live mode is inlined directly in :class:`ExecutionService` and no longer
needs a dedicated adapter (the previous ``LiveOMSAdapter`` was a pure
pass-through). Paper and replay modes remain here because they supply
their own simulated fill callbacks.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from application.execution.simulated_fill import make_simulated_submit_fn
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderResult

logger = logging.getLogger(__name__)


class ExecutionModeAdapter(ABC):
    """Common interface for order execution across trading modes."""

    @abstractmethod
    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Any | None = None,
    ) -> OrderResult:
        """Place an order using the mode-appropriate execution path."""


class PaperOMSAdapter(ExecutionModeAdapter):
    """Paper trading — routes through OMS with simulated submit_fn."""

    def __init__(self, trading_context: TradingContext) -> None:
        self._ctx = trading_context

    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Any | None = None,
    ) -> OrderResult:
        sim_fn = submit_fn or make_simulated_submit_fn(command, order_id_prefix="paper")
        return self._ctx.order_manager.place_order(command, submit_fn=sim_fn)


class ReplayOMSAdapter(ExecutionModeAdapter):
    """Replay/backtest — routes through OMS for zero-parity with live."""

    def __init__(self, trading_context: TradingContext) -> None:
        self._ctx = trading_context

    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Any | None = None,
    ) -> OrderResult:
        sim_fn = submit_fn or make_simulated_submit_fn(command, order_id_prefix="bt")
        return self._ctx.order_manager.place_order(command, submit_fn=sim_fn)


def create_execution_adapter(
    mode: str,
    trading_context: TradingContext,
) -> ExecutionModeAdapter:
    """Factory for execution mode adapters.

    Note: ``"live"`` mode is NOT handled here — it is inlined directly
    in :class:`~brokers.common.execution.execution_service.ExecutionService`.
    Callers that need a live adapter should call
    ``OrderManager.place_order`` directly.
    """
    mode = mode.lower()
    if mode == "paper":
        return PaperOMSAdapter(trading_context)
    if mode in ("replay", "backtest"):
        return ReplayOMSAdapter(trading_context)
    raise ValueError(f"Unknown execution mode: {mode}. For live mode, call OrderManager.place_order directly.")


class LiveOMSAdapter(ExecutionModeAdapter):
    """Stub for backward compatibility — live mode is inlined in ExecutionService.
    
    This class exists only for test compatibility. Do not use in new code.
    """
    
    def __init__(self, trading_context: TradingContext):
        self._ctx = trading_context
    
    def place_order(
        self,
        command: OmsOrderCommand,
        submit_fn: Any | None = None,
    ) -> OrderResult:
        raise NotImplementedError(
            "LiveOMSAdapter is deprecated. Call OrderManager.place_order() directly."
        )
