"""CLI Broker Facade — order routing for the CLI layer.

Extracted from BrokerService to reduce complexity and enable independent
testing.  This module handles:

- Order placement via the OMS OrderManager
- Order cancellation
- Order / trade retrieval and status aggregation
- Gateway availability guards
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


class CliBrokerFacade:
    """Thin facade that routes order commands through the OMS.

    Every method receives the owning :class:`BrokerService` via the
    constructor so it can read shared state (gateway, trading_context,
    live_actionable, etc.).
    """

    def __init__(self, service: BrokerService) -> None:
        self._svc = service

    # ------------------------------------------------------------------
    # Internal helpers (moved from BrokerService private methods)
    # ------------------------------------------------------------------

    def oms_orders(self) -> list:
        """Return orders from the central OrderManager, falling back to the
        gateway order book when no TradingContext is wired (backward compat)."""
        self._svc._ensure_initialized()
        if self._svc._trading_context is not None:
            return self._svc._trading_context.order_manager.get_orders()
        gw = self._svc._gateway
        if gw is None:
            return []
        return gw.get_orderbook()

    def oms_trades(self) -> list:
        self._svc._ensure_initialized()
        gw = self._svc._gateway
        if gw is None:
            return []
        return gw.get_trade_book()

    def ensure_oms_gateway(self):
        self._svc._ensure_initialized()
        gw = self._svc._gateway
        if gw is None:
            if self._svc._trading_context is not None:
                raise RuntimeError("TradingContext does not expose a gateway.")
            raise RuntimeError(
                "No broker gateway available. Configure .env.local with valid credentials."
            )
        return gw

    # ------------------------------------------------------------------
    # Public order / trade API
    # ------------------------------------------------------------------

    def get_order_stats(self) -> dict[str, int]:
        """Collect order counts by status (mirrors retired OmsService)."""
        from domain import OrderStatus

        orders = self.oms_orders()
        stats = {
            "pending": 0,
            "open": 0,
            "filled": 0,
            "rejected": 0,
            "cancelled": 0,
        }
        for o in orders:
            status = o.status
            if status == OrderStatus.OPEN:
                stats["open"] += 1
            elif status == OrderStatus.PARTIALLY_FILLED:
                stats["pending"] += 1
            elif status == OrderStatus.FILLED:
                stats["filled"] += 1
            elif status == OrderStatus.REJECTED:
                stats["rejected"] += 1
            elif status == OrderStatus.CANCELLED:
                stats["cancelled"] += 1
        return stats

    def get_orders(self, status_filter: str | None = None) -> list:
        """Fetch orders with optional status filter (mirrors retired OmsService)."""
        from domain import OrderStatus

        orders = self.oms_orders()
        if not status_filter:
            return orders

        filt = status_filter.upper()
        if filt == "PENDING":
            return [
                o for o in orders if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
            ]
        if filt == "FILLED":
            return [o for o in orders if o.status == OrderStatus.FILLED]
        return [o for o in orders if o.status.value == filt]

    def get_trades(self) -> list:
        """Fetch trades for the day (mirrors retired OmsService)."""
        return self.oms_trades()

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 0,
        price: Decimal | None = None,
        order_type: str = "MARKET",
    ):
        """Place order via the OMS OrderManager.

        The central OMS is the SINGLE entry point for order placement. The
        broker gateway is consulted by the OMS's ``submit_fn`` (which the OMS
        uses to dispatch to Dhan), so callers do not bypass risk checks,
        idempotency, or event-bus publishing.

        This method refuses to dispatch when the runtime is not
        ``live_actionable`` (production readiness gate failed, or the OMS has
        not been wired into a ``TradingContext``).
        """
        self._svc._ensure_initialized()
        if not self._svc._live_actionable:
            raise RuntimeError(
                "OMS refused: runtime is not live-actionable. "
                "Run `tradex doctor` for the production readiness report; "
                "address every failing check before placing orders."
            )
        if self._svc._trading_context is not None:
            from domain import (
                OrderType as Ot,
            )
            from domain import (
                ProductType as Pt,
            )
            from domain import Side
            from application.oms.order_manager import OrderRequest

            try:
                ot = Ot(order_type)
            except ValueError:
                ot = Ot.MARKET
            req = OrderRequest(
                symbol=symbol,
                exchange=exchange,
                side=Side(side) if isinstance(side, str) else side,
                quantity=quantity,
                price=price if price is not None else Decimal("0"),
                order_type=ot,
                product_type=Pt.INTRADAY,
            )
            gw = self._svc._gateway
            if gw is None:
                raise RuntimeError(
                    "No broker gateway available. Configure .env.local with valid credentials."
                )

            def _submit(r):
                return gw.place_order(
                    symbol=r.symbol,
                    exchange=r.exchange,
                    side=r.side,
                    quantity=r.quantity,
                    price=r.price,
                    order_type=r.order_type,
                    product_type=r.product_type,
                )

            result = self._svc._trading_context.order_manager.place_order(req, submit_fn=_submit)
            if not result.success:
                raise RuntimeError(f"OMS rejected order: {result.error}")
            return result.order
        # Safe-to-trade: never bypass OMS (no bare gateway place_order)
        raise RuntimeError(
            "OMS refused: TradingContext / OrderManager not wired. "
            "Cannot place orders without the institutional order spine."
        )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order (mirrors retired OmsService)."""
        self._svc._ensure_initialized()
        if self._svc._trading_context is not None:
            result = self._svc._trading_context.order_manager.cancel_order(order_id)
            return result.success
        raise RuntimeError(
            "OMS refused: TradingContext / OrderManager not wired. "
            "Cannot cancel orders without the institutional order spine."
        )
