"""Unified execution facade — single entry for OMS-first order placement."""

from __future__ import annotations

from typing import Any

from application.execution.execution_mode_adapter import (
    ExecutionModeAdapter,
    create_execution_adapter,
)
from application.execution.gateway_submit import make_gateway_submit_fn
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain.ports.broker_gateway import OrderTransportPort


class ExecutionService:
    """Orchestrates order placement and cancellation through OMS + mode adapters.

    For ``"live"`` mode, ``place_order`` calls ``OrderManager.place_order``
    directly (inlining the previous ``LiveOMSAdapter`` pass-through). For
    ``"paper"`` and ``"replay"`` modes, it delegates to a mode adapter
    that supplies a simulated fill callback.
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

    def _live_submit_fn(self) -> Any:
        return make_gateway_submit_fn(self._gateway, transport_only=True)

    def place_order(
        self,
        command: OmsOrderCommand,
        *,
        submit_fn: Any | None = None,
    ) -> OrderResult:
        """Place an order via the configured execution mode.

        Live mode calls ``OrderManager.place_order`` directly with a
        gateway-backed ``submit_fn``. Paper/replay mode delegates to a
        mode adapter that supplies its own simulated fill callback.
        """
        if self._mode == "live":
            fn = submit_fn or self._live_submit_fn()
            return self._ctx.order_manager.place_order(command, submit_fn=fn)
        if self._adapter is not None:
            return self._adapter.place_order(command, submit_fn=submit_fn)
        # Fallback — should not happen for known modes
        return self._ctx.order_manager.place_order(command, submit_fn=submit_fn)

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order through the OMS."""
        return self._ctx.order_manager.cancel_order(order_id)
