"""ExecutionEngine — single entry point for order execution.

Mode-agnostic: both live and sim go through the same place/cancel/modify
path. The only difference is the injected FillSource.
"""

from __future__ import annotations

import logging

from application.execution.fill_source import FillSource
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand, OrderManager, OrderResult
from domain.ports.execution_target import ExecutionTarget

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Unified execution engine — single place/cancel/modify entry.

    Replaces the mode-branched ExecutionService with a single path
    that delegates to OrderManager + FillSource.
    """

    def __init__(
        self,
        fill_source: FillSource | ExecutionTarget,
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

    def place_order(self, command: OmsOrderCommand) -> OrderResult:
        """Place an order through the unified engine."""
        from application.execution.spine import place_order_spine

        return place_order_spine(self._ctx.order_manager, command, self._fill_source)

    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order through the unified engine."""
        from application.execution.cancel_order_use_case import CancelOrderUseCase

        cancel_fn = getattr(self._fill_source, "cancel_fn", None)
        resolved = cancel_fn() if callable(cancel_fn) else None
        return CancelOrderUseCase(self._ctx.order_manager, cancel_fn=resolved).execute(order_id)

    def modify_order(self, request: object) -> OrderResult:
        """Modify an order through the unified engine."""
        modify_fn = getattr(self._fill_source, "modify_fn", None)
        resolved = modify_fn() if callable(modify_fn) else None
        return self._ctx.order_manager.modify_order(request, modify_fn=resolved)

    def apply_mass_status(
        self,
        orders: list | None = None,
        positions: list | None = None,
        funds: dict | None = None,
    ) -> list:
        """Apply broker mass-status snapshot, healing local OMS drift (F4).

        Upserts missing/divergent orders and positions into the OMS so a
        missed websocket update cannot leave the local book permanently
        behind broker truth. Returns the drift items that were detected
        (and healed).
        """
        from domain.symbols import normalize_exchange, normalize_symbol

        drift_items: list = []
        om = self._ctx.order_manager
        pm = self._ctx.position_manager

        if orders:
            for order in orders:
                order_id = getattr(order, "order_id", None)
                if not order_id:
                    continue
                existing = om.get_order(order_id) if hasattr(om, "get_order") else None
                if existing is None:
                    drift_items.append(
                        {
                            "kind": "missing_local_order",
                            "order_id": order_id,
                            "severity": "HIGH",
                        }
                    )
                    try:
                        om.upsert_order(order)
                    except Exception as exc:
                        logger.warning("mass_status_order_heal_failed %s: %s", order_id, exc)
                elif existing.status != getattr(
                    order, "status", existing.status
                ) or existing.filled_quantity != getattr(
                    order, "filled_quantity", existing.filled_quantity
                ):
                    drift_items.append(
                        {
                            "kind": "order_status_mismatch",
                            "order_id": order_id,
                            "severity": "HIGH",
                        }
                    )
                    try:
                        om.upsert_order(order)
                    except Exception as exc:
                        logger.warning("mass_status_order_heal_failed %s: %s", order_id, exc)

        if positions:
            for pos in positions:
                symbol = getattr(pos, "symbol", "") or ""
                if not symbol:
                    continue
                exchange = getattr(pos, "exchange", "NSE") or "NSE"
                qty = int(getattr(pos, "quantity", 0) or 0)
                avg_price = getattr(pos, "avg_price", 0)
                ltp = getattr(pos, "ltp", 0)
                local = (
                    pm.get_position(normalize_symbol(symbol), normalize_exchange(exchange))
                    if hasattr(pm, "get_position")
                    else None
                )
                payload = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "quantity": qty,
                    "avg_price": str(avg_price),
                    "ltp": str(ltp),
                }
                if local is None and qty != 0:
                    drift_items.append(
                        {
                            "kind": "missing_local_position",
                            "symbol": symbol,
                            "severity": "HIGH",
                        }
                    )
                    try:
                        pm.upsert_position(payload)
                    except Exception as exc:
                        logger.warning("mass_status_position_heal_failed %s: %s", symbol, exc)
                elif local is not None and local.quantity != qty:
                    drift_items.append(
                        {
                            "kind": "position_quantity_mismatch",
                            "symbol": symbol,
                            "severity": "HIGH",
                        }
                    )
                    try:
                        pm.upsert_position(payload)
                    except Exception as exc:
                        logger.warning("mass_status_position_heal_failed %s: %s", symbol, exc)
                else:
                    drift_items.append(
                        {
                            "kind": "position_update",
                            "symbol": symbol,
                            "severity": "MEDIUM",
                        }
                    )
                    # Still sync LTP / avg from broker when present.
                    if local is not None:
                        try:
                            pm.upsert_position(payload)
                        except Exception as exc:
                            logger.warning("mass_status_position_sync_failed %s: %s", symbol, exc)

        return drift_items
