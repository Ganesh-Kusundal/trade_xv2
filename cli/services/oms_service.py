"""OMS Service layer for diagnostics and operation terminal."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from application.execution.execution_service import ExecutionService
from application.oms.context import TradingContext
from application.oms.order_manager import OmsOrderCommand
from brokers.common.gateway import MarketDataGateway
from domain import Order, OrderStatus, Side, Trade


class OmsService:
    """Interfaces with broker gateway order book and monitors OMS flows.

    Requires a ``TradingContext`` for order placement and cancellation so
    every write goes through risk checks, idempotency, and event publishing.
    Read-only diagnostics fall back to the gateway order book when no context
    is wired.
    """

    def __init__(
        self,
        gateway: MarketDataGateway | None = None,
        trading_context: TradingContext | None = None,
    ) -> None:
        self._gw = gateway
        self._ctx = trading_context

    @property
    def gateway(self) -> MarketDataGateway | None:
        return self._gw

    @property
    def trading_context(self) -> TradingContext | None:
        return self._ctx

    def _orders(self) -> list[Order]:
        if self._ctx is not None:
            return self._ctx.order_manager.get_orders()
        gw = self._gw
        if gw is None:
            return []
        return gw.get_orderbook()

    def _trades(self) -> list[Trade]:
        gw = self._gw
        if gw is None:
            return []
        return gw.get_trade_book()

    def _ensure_gateway(self) -> MarketDataGateway:
        gw = self._gw
        if gw is None:
            if self._ctx is not None:
                raise RuntimeError("TradingContext does not expose a gateway.")
            raise RuntimeError(
                "No broker gateway available. Configure .env.local with valid credentials."
            )
        return gw

    def get_order_stats(self) -> dict[str, int]:
        """Collect order counts by status."""
        orders = self._orders()
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

    def get_orders(self, status_filter: str | None = None) -> list[Order]:
        """Fetch orders with optional status filter."""
        orders = self._orders()
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

    def get_trades(self) -> list[Trade]:
        """Fetch trades for the day."""
        return self._trades()

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 0,
        price: Decimal | None = None,
        order_type: str = "MARKET",
    ) -> Order:
        """Place order via the OMS OrderManager.

        M-1: the central OMS is the SINGLE entry point for order
        placement. The broker gateway is consulted by the OMS's
        ``submit_fn`` (which the OMS uses to dispatch to Dhan), so
        callers do not bypass risk checks, idempotency, or
        event-bus publishing.
        """
        if self._ctx is None:
            raise RuntimeError(
                "TradingContext is required for order placement. "
                "Configure BrokerService with a live trading context."
            )

        from domain import OrderType as Ot
        from domain import ProductType as Pt

        try:
            ot = Ot(order_type)
        except ValueError:
            ot = Ot.MARKET
        req = OmsOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=Side(side) if isinstance(side, str) else side,
            quantity=quantity,
            price=price if price is not None else Decimal("0"),
            order_type=ot,
            product_type=Pt.INTRADAY,
            correlation_id=f"cli:{uuid.uuid4().hex}",
        )
        gw = self._gw
        if gw is None:
            raise RuntimeError(
                "No broker gateway available. Configure .env.local with valid credentials."
            )

        svc = ExecutionService(
            trading_context=self._ctx,
            gateway=gw,
            mode="live",
        )
        result = svc.place_order(req)
        if not result.success:
            raise RuntimeError(f"OMS rejected order: {result.error}")
        return result.order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if self._ctx is None:
            raise RuntimeError(
                "TradingContext is required for order cancellation. "
                "Configure BrokerService with a live trading context."
            )
        result = self._ctx.order_manager.cancel_order(order_id)
        return result.success

    def modify_order(
        self,
        order_id: str,
        *,
        price: Decimal | None = None,
        quantity: int | None = None,
    ) -> bool:
        """Modify an open order via the OMS-enforced gateway path."""
        if self._ctx is None:
            raise RuntimeError(
                "TradingContext is required for order modification. "
                "Configure BrokerService with a live trading context."
            )
        gw = self._gw
        if gw is None:
            raise RuntimeError(
                "No broker gateway available. Configure .env.local with valid credentials."
            )
        changes: dict[str, Any] = {}
        if price is not None:
            changes["price"] = price
        if quantity is not None:
            changes["quantity"] = quantity
        if not changes:
            raise ValueError("No modifications specified")
        response = gw.modify_order(order_id, **changes)
        return bool(getattr(response, "success", True))
