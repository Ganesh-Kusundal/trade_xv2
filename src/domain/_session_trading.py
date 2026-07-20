"""Trading convenience methods for Session (buy/sell/place/cancel/modify)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.enums import OrderType, ProductType, Side
from domain.orders.intent import OrderIntent
from domain.orders.placement import build_order_intent, place_via_order_service

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument
    from domain.ports.protocols import OrderResult


def _as_side(side: str | Side) -> Side:
    if isinstance(side, Side):
        return side
    return Side(str(side).upper())


def _as_order_type(order_type: str | OrderType) -> OrderType:
    if isinstance(order_type, OrderType):
        return order_type
    return OrderType(str(order_type).upper())


def _as_product_type(product_type: str | ProductType) -> ProductType:
    if isinstance(product_type, ProductType):
        return product_type
    return ProductType(str(product_type).upper())


class SessionTradingMixin:
    """Order intent building + submission convenience methods."""

    def _assert_orders_enabled(self) -> None:
        if self._status is not None and not getattr(self._status, "orders_enabled", True):
            mode = getattr(self._status, "mode", "market")
            raise RuntimeError(
                "ORDERS_DISABLED: Session is market-data only "
                f"(mode={mode!r}). Reconnect with mode='trade' when ready to trade "
                "(requires process OMS via CLI/API)."
            )

    def intent(
        self,
        instrument: Instrument,
        side: str | Side,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
        trigger_price: Decimal | None = None,
        correlation_id: str | None = None,
    ) -> OrderIntent:
        """Build an :class:`OrderIntent` without submitting it."""
        return build_order_intent(
            instrument,
            _as_side(side),
            quantity,
            price=price,
            order_type=_as_order_type(order_type),
            product_type=_as_product_type(product_type),
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

    def place(self, intent: OrderIntent) -> OrderResult:
        """Submit an intent via the injected order-command fn or OMS (fallback)."""
        self._assert_orders_enabled()

        fn = self._order_command_fn if hasattr(self, "_order_command_fn") else None
        if callable(fn):
            return fn(intent)

        if self._order_service is not None:
            return place_via_order_service(self._order_service, intent)

        raise RuntimeError(
            "No order_service (OMS) configured for this session. "
            "Use tradex.connect(...) which wires OrderIntent → Risk → OMS → Execution."
        )

    def cancel(self, order_id: str) -> OrderResult:
        """Cancel via OMS OrderServicePort (fail closed in market mode)."""
        self._assert_orders_enabled()
        if self._order_service is None:
            raise RuntimeError(
                "No order_service (OMS) configured. Use tradex.connect(..., mode='sim'|'trade')."
            )
        cancel = getattr(self._order_service, "cancel", None)
        if not callable(cancel):
            raise RuntimeError("OrderServicePort does not implement cancel()")
        return cancel(order_id)

    def modify(
        self,
        order_id: str,
        *,
        quantity: int | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        order_type: str | OrderType | None = None,
    ) -> OrderResult:
        """Modify via OMS OrderServicePort (fail closed in market mode)."""
        from domain.orders.requests import ModifyOrderRequest

        self._assert_orders_enabled()
        if self._order_service is None:
            raise RuntimeError(
                "No order_service (OMS) configured. Use tradex.connect(..., mode='sim'|'trade')."
            )
        modify = getattr(self._order_service, "modify", None)
        if not callable(modify):
            raise RuntimeError("OrderServicePort does not implement modify()")
        ot = None
        if order_type is not None:
            ot = (
                order_type
                if isinstance(order_type, OrderType)
                else OrderType(str(order_type).upper())
            )
        return modify(
            ModifyOrderRequest(
                order_id=order_id,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                order_type=ot,
            )
        )

    def _place_order(
        self,
        instrument: Instrument,
        side: str | Side,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
        trigger_price: Decimal | None = None,
    ) -> Any:
        """Build OrderIntent and place through the institutional spine."""
        intent = self.intent(
            instrument,
            side,
            quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            trigger_price=trigger_price,
        )
        return self.place(intent)

    def buy(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
    ) -> Any:
        """Place a buy order (OrderIntent → OMS when wired)."""
        return self._place_order(instrument, Side.BUY, quantity, price, order_type, product_type)

    def sell(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal | None = None,
        order_type: str | OrderType = OrderType.LIMIT,
        product_type: str | ProductType = ProductType.INTRADAY,
    ) -> Any:
        """Place a sell order (OrderIntent → OMS when wired)."""
        return self._place_order(instrument, Side.SELL, quantity, price, order_type, product_type)

    def market(
        self,
        instrument: Instrument,
        quantity: int,
        side: str | Side = Side.BUY,
    ) -> Any:
        """Place a market order for the given instrument."""
        resolved = _as_side(side)
        return self._place_order(instrument, resolved, quantity, order_type=OrderType.MARKET)

    def limit(
        self,
        instrument: Instrument,
        quantity: int,
        price: Decimal,
        side: str | Side = Side.BUY,
    ) -> Any:
        """Place a limit order for the given instrument."""
        resolved = _as_side(side)
        return self._place_order(
            instrument, resolved, quantity, price=price, order_type=OrderType.LIMIT
        )

    def stop_loss(
        self,
        instrument: Instrument,
        quantity: int,
        trigger_price: Decimal,
        side: str | Side = Side.BUY,
    ) -> Any:
        """Place a stop-loss market order for the given instrument."""
        resolved = _as_side(side)
        return self._place_order(
            instrument,
            resolved,
            quantity,
            order_type=OrderType.STOP_LOSS_MARKET,
            trigger_price=trigger_price,
        )
