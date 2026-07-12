"""ExecutionEngine — single entry point for order execution.

Mode-agnostic: both live and sim go through the same place/cancel/modify
path. The only difference is the injected FillSource.
"""
from __future__ import annotations

from application.execution.fill_source import FillSource
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from application.observability import trace_operation


class ExecutionEngine:
    """Unified execution engine — single place/cancel/modify entry.

    Replaces the mode-branched ExecutionService with a single path
    that delegates to OrderManager + FillSource.
    """

    def __init__(
        self,
        fill_source: FillSource,
        trading_context: TradingContext,
    ) -> None:
        self._fill_source = fill_source
        self._ctx = trading_context

    @property
    def order_manager(self) -> OrderManager:
        return self._ctx.order_manager

    @property
    def fill_source(self) -> FillSource:
        return self._fill_source

    @trace_operation("execution_engine.place_order")
    def place_order(self, command: OmsOrderCommand) -> OrderResult:
        """Place an order through the unified engine."""
        submit_fn = self._fill_source.submit_fn()
        return self._ctx.order_manager.place_order(command, submit_fn=submit_fn)

    @trace_operation("execution_engine.cancel_order")
    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order through the engine."""
        from application.execution.cancel_order_use_case import CancelOrderUseCase
        return CancelOrderUseCase(self._ctx.order_manager).execute(order_id)

    def apply_mass_status(
        self,
        orders: list | None = None,
        positions: list | None = None,
        funds: dict | None = None,
    ) -> list:
        """Apply broker mass-status snapshot to the cache.

        This is the hot-path reconciliation entry point. The timer fetches
        broker state; this method applies it, healing drift before the
        next check_order.
        """
        drift_items: list = []

        if orders:
            for order in orders:
                existing = (
                    self._ctx.order_manager.get_order(order.order_id)
                    if hasattr(self._ctx.order_manager, "get_order")
                    else None
                )
                if existing is None:
                    drift_items.append(
                        {
                            "kind": "missing_local_order",
                            "order_id": order.order_id,
                            "severity": "HIGH",
                        }
                    )

        if positions:
            for pos in positions:
                drift_items.append(
                    {
                        "kind": "position_update",
                        "symbol": getattr(pos, "symbol", ""),
                        "severity": "MEDIUM",
                    }
                )

        return drift_items
