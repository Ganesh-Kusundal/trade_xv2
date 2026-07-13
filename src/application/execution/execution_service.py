"""Unified execution facade — single entry for OMS-first order placement.

.. deprecated::
    Use :class:`ExecutionEngine` with :class:`FillSource` instead.
    This module is retained for backtest/replay compatibility only.
"""

from __future__ import annotations

from collections.abc import Callable

from application.execution.cancel_order_use_case import CancelOrderUseCase
from application.execution.execution_mode_adapter import (
    ExecutionModeAdapter,
    create_execution_adapter,
)
from application.execution.gateway_submit import make_gateway_submit_fn
from application.execution.place_order_use_case import PlaceOrderUseCase
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain import Order
from domain.ports.broker_gateway import OrderTransportPort
from application.observability import trace_operation


class ExecutionService:
    """Orchestrates order placement and cancellation through OMS + mode adapters.

    For ``"live"`` mode, ``place_order`` goes through ``PlaceOrderUseCase``
    (OMS + optional event publish). For ``"paper"`` and ``"replay"`` modes,
    it delegates to a mode adapter that supplies a simulated fill callback.
    """

    def __init__(
        self,
        *,
        trading_context: TradingContext,
        gateway: OrderTransportPort,
        mode: str = "live",
    ) -> None:
        self._ctx = trading_context
        self._gateway = gateway
        self._mode = mode
        # Only paper/replay modes need a dedicated adapter (simulated fills).
        # Live mode bypasses the adapter entirely — see place_order().
        self._adapter: ExecutionModeAdapter | None = (
            create_execution_adapter(mode, trading_context) if mode != "live" else None
        )

    @property
    def order_manager(self) -> OrderManager:
        return self._ctx.order_manager

    @property
    def mode(self) -> str:
        return self._mode

    def _live_submit_fn(self) -> Callable[[OmsOrderCommand], Order]:
        return make_gateway_submit_fn(self._gateway)

    @trace_operation("execution.place_order")
    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Callable[[OmsOrderCommand], Order] | None = None,
    ) -> OrderResult:
        """Place an order via the configured execution mode.

        Live mode routes through ``PlaceOrderUseCase`` with a gateway-backed
        ``submit_fn``. Paper/replay mode delegates to a mode adapter that
        supplies its own simulated fill callback.
        """
        if self._mode == "live":
            fn = submit_fn or self._live_submit_fn()
            return PlaceOrderUseCase(
                self._ctx.order_manager,
                submit_fn=fn,
            ).execute(command)
        if self._adapter is not None:
            return self._adapter.place_order(command, submit_fn=submit_fn)
        # Fallback — should not happen for known modes
        return PlaceOrderUseCase(
            self._ctx.order_manager,
            submit_fn=submit_fn,
        ).execute(command)

    @trace_operation("execution.cancel_order")
    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order through CancelOrderUseCase → OMS."""
        return CancelOrderUseCase(self._ctx.order_manager).execute(order_id)
