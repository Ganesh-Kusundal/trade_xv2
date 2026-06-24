"""Unified execution facade — single entry for OMS-first order placement."""

from __future__ import annotations

from typing import Any

from application.execution.execution_mode_adapter import (
    ExecutionModeAdapter,
    LiveOMSAdapter,
    create_execution_adapter,
)
from application.execution.gateway_submit import make_gateway_submit_fn
from domain.ports.broker_gateway import OrderTransportPort
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult


class ExecutionService:
    """Orchestrates order placement and cancellation through OMS + mode adapters."""

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
        self._adapter: ExecutionModeAdapter = create_execution_adapter(mode, trading_context)

    @property
    def order_manager(self) -> OrderManager:
        return self._ctx.order_manager

    @property
    def mode(self) -> str:
        return self._mode

    def _live_submit_fn(self) -> Any:
        return make_gateway_submit_fn(self._gateway, transport_only=True)

    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Any | None = None,
    ) -> OrderResult:
        """Place an order via the configured execution mode."""
        if isinstance(self._adapter, LiveOMSAdapter):
            fn = submit_fn or self._live_submit_fn()
            return self._adapter.place_order(command, submit_fn=fn)
        return self._adapter.place_order(command, submit_fn=submit_fn)

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order through the OMS."""
        return self._ctx.order_manager.cancel_order(order_id)
