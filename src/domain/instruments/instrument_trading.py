"""InstrumentTradingMixin — order placement & management methods.

Extracted from the Instrument god class (KD-202).
"""

from __future__ import annotations

import logging
import weakref
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.enums import OrderType, ProductType, Side
from domain.orders.placement import build_order_intent, place_via_order_service

if TYPE_CHECKING:
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import OrderResult

logger = logging.getLogger(__name__)


class InstrumentTradingMixin:
    """Mixin providing order placement & management methods for Instrument.

    Expects these attributes on ``self`` (provided by ``Instrument.__init__``):

        _order_service_ref, symbol, _resolve_order_service()
    """

    # ── Attribute declarations (provided by concrete class) ────────────

    _order_service_ref: weakref.ref | None
    symbol: str

    def _resolve_order_service(self) -> OrderServicePort | None:  # pragma: no cover
        ...

    # ── Order Entry ───────────────────────────────────────────────────

    def buy(
        self,
        quantity: int,
        price: Decimal | None = None,
        order_type: OrderType | str = OrderType.LIMIT,
        product_type: ProductType | str = ProductType.INTRADAY,
        *,
        correlation_id: str | None = None,
    ) -> OrderResult:
        """Place a buy via OrderServicePort only (never ExecutionProvider)."""
        return self._place(Side.BUY, quantity, price, order_type, product_type, correlation_id)

    def sell(
        self,
        quantity: int,
        price: Decimal | None = None,
        order_type: OrderType | str = OrderType.LIMIT,
        product_type: ProductType | str = ProductType.INTRADAY,
        *,
        correlation_id: str | None = None,
    ) -> OrderResult:
        """Place a sell via OrderServicePort only (never ExecutionProvider)."""
        return self._place(Side.SELL, quantity, price, order_type, product_type, correlation_id)

    def market(
        self,
        quantity: int,
        side: Side | str = Side.BUY,
        *,
        product_type: ProductType | str = ProductType.INTRADAY,
        correlation_id: str | None = None,
    ) -> OrderResult:
        """Place a market order via OMS only."""
        s = side if isinstance(side, Side) else Side(str(side).upper())
        return self._place(
            s, quantity, None, OrderType.MARKET, product_type, correlation_id
        )

    def limit(
        self,
        quantity: int,
        price: Decimal,
        side: Side | str = Side.BUY,
        *,
        product_type: ProductType | str = ProductType.INTRADAY,
        correlation_id: str | None = None,
    ) -> OrderResult:
        """Place a limit order via OMS only."""
        s = side if isinstance(side, Side) else Side(str(side).upper())
        return self._place(
            s, quantity, price, OrderType.LIMIT, product_type, correlation_id
        )

    def stop_loss(
        self,
        quantity: int,
        trigger_price: Decimal,
        side: Side | str = Side.BUY,
        *,
        product_type: ProductType | str = ProductType.INTRADAY,
        correlation_id: str | None = None,
    ) -> OrderResult:
        """Place a stop-loss market order via OMS only."""
        s = side if isinstance(side, Side) else Side(str(side).upper())
        return self._place(
            s,
            quantity,
            None,
            OrderType.STOP_LOSS_MARKET,
            product_type,
            correlation_id,
            trigger_price=trigger_price,
        )

    # ── Order Management ──────────────────────────────────────────────

    def cancel(self, order_id: str) -> OrderResult:
        """Cancel an open order via OrderServicePort (OMS), never ExecutionProvider."""
        from domain.errors import NotConfiguredError

        osvc = self._require_order_service()
        cancel = getattr(osvc, "cancel", None)
        if not callable(cancel):
            raise NotConfiguredError(
                "OrderServicePort does not implement cancel(); upgrade OMS wiring."
            )
        return cancel(order_id)

    def modify(
        self,
        order_id: str,
        *,
        quantity: int | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        order_type: OrderType | str | None = None,
    ) -> OrderResult:
        """Modify an open order via OrderServicePort (OMS)."""
        from domain.errors import NotConfiguredError
        from domain.orders.requests import ModifyOrderRequest

        osvc = self._require_order_service()
        modify = getattr(osvc, "modify", None)
        if not callable(modify):
            raise NotConfiguredError(
                "OrderServicePort does not implement modify(); upgrade OMS wiring."
            )
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

    def _require_order_service(self) -> OrderServicePort:
        """Resolve OMS or raise ORDERS_DISABLED / NotConfiguredError."""
        from domain.errors import NotConfiguredError

        osvc = self._resolve_order_service()
        if osvc is not None:
            # Market-mode ambient: even if something stamped OMS, still refuse
            try:
                from domain.ports.session_context import get_ambient_session

                ambient = get_ambient_session()
                st = getattr(ambient, "status", None) if ambient is not None else None
                if st is not None and not getattr(st, "orders_enabled", True):
                    raise NotConfiguredError(
                        "ORDERS_DISABLED: Session is market-data only "
                        f"(mode={getattr(st, 'mode', 'market')!r}). "
                        "Reconnect with mode='trade' when ready to trade."
                    )
            except NotConfiguredError:
                raise
            except Exception:
                pass
            return osvc
        try:
            from domain.ports.session_context import get_ambient_session

            ambient = get_ambient_session()
            st = getattr(ambient, "status", None) if ambient is not None else None
            if st is not None and not getattr(st, "orders_enabled", True):
                raise NotConfiguredError(
                    "ORDERS_DISABLED: Session is market-data only "
                    f"(mode={getattr(st, 'mode', 'market')!r}). "
                    "Reconnect with mode='trade' when ready to trade."
                )
        except NotConfiguredError:
            raise
        except Exception:
            pass
        raise NotConfiguredError(
            "Instrument has no OrderServicePort (OMS). "
            "Use tradex.connect(..., mode='sim'|'trade')."
        )

    def _place(
        self,
        side: Side,
        quantity: int,
        price: Decimal | None,
        order_type: OrderType | str,
        product_type: ProductType | str,
        correlation_id: str | None,
        *,
        trigger_price: Decimal | None = None,
    ) -> OrderResult:
        from domain.errors import NotConfiguredError

        ot = order_type if isinstance(order_type, OrderType) else OrderType(str(order_type).upper())
        pt = (
            product_type
            if isinstance(product_type, ProductType)
            else ProductType(str(product_type).upper())
        )
        osvc = self._require_order_service()
        intent = build_order_intent(
            self,
            side,
            quantity,
            price=price,
            order_type=ot,
            product_type=pt,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )
        return place_via_order_service(osvc, intent)
