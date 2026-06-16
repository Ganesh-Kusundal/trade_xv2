"""Simulated order management for paper trading."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from brokers.common.core.domain import (
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Side,
    Trade,
    Validity,
)

from .paper_market_data import PaperMarketData


class PaperOrders:
    """Simulates order placement with instant fills at quoted prices.

    When ``order_manager`` and ``position_manager`` are supplied, the paper
    engine publishes canonical events and delegates state ownership to those
    managers. Otherwise it keeps the state internally for backward
    compatibility.
    """

    def __init__(
        self,
        market_data: PaperMarketData,
        positions: dict[str, Position],
        order_manager: object | None = None,
        position_manager: object | None = None,
    ) -> None:
        self._md = market_data
        self._positions = positions
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._orders: list[Order] = []
        self._trades: list[Trade] = []
        self._order_seq = 0
        self._trade_seq = 0
        self._lock = RLock()

    def _risk_check(self, order: Order) -> tuple[bool, str | None]:
        """Delegate to the central risk manager if available."""
        risk = getattr(self._order_manager, "risk_manager", None)
        if risk is None:
            return True, None
        result = risk.check_order(order)
        return result.allowed, result.reason

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str | OrderType = "MARKET",
        product_type: str | ProductType = "INTRADAY",
        validity: str | Validity = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> Order:
        if isinstance(side, str):
            side = Side(side.upper())
        if isinstance(order_type, str):
            order_type = OrderType(order_type.upper())
        if isinstance(product_type, str):
            product_type = ProductType(product_type.upper())
        if isinstance(validity, str):
            validity = Validity(validity.upper())

        if price > 0 and order_type == OrderType.LIMIT:
            fill_price = price
        else:
            fill_price = self._md.get_ltp(symbol, exchange)

        with self._lock:
            self._order_seq += 1
            order_id = f"PPR-{self._order_seq:06d}"

            preview_order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                product_type=product_type,
                validity=validity,
                correlation_id=correlation_id,
            )
            allowed, reason = self._risk_check(preview_order)
            if not allowed:
                rejected = replace(
                    preview_order,
                    status=OrderStatus.REJECTED,
                    reject_reason=reason or "Risk check failed",
                )
                self._orders.append(rejected)
                if self._order_manager is not None:
                    self._order_manager.upsert_order(rejected)
                return rejected

            order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                filled_quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                status=OrderStatus.FILLED,
                timestamp=datetime.now(timezone.utc),
                product_type=product_type,
                validity=validity,
                avg_price=fill_price,
                correlation_id=correlation_id,
            )

            self._orders.append(order)
            if self._order_manager is not None:
                self._order_manager.upsert_order(order)

            self._trade_seq += 1
            trade = Trade(
                trade_id=f"PPR-T-{self._trade_seq:06d}",
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=fill_price,
                trade_value=fill_price * quantity,
                timestamp=datetime.now(timezone.utc),
                product_type=product_type,
            )
            self._trades.append(trade)
            if self._order_manager is not None:
                self._order_manager.record_trade(trade)

            if self._position_manager is not None:
                self._position_manager.apply_trade(trade)
            self._positions = self._update_position(
                symbol, exchange, side, quantity, fill_price, product_type
            )

            return order

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            for i, o in enumerate(self._orders):
                if o.order_id == order_id and o.status == OrderStatus.OPEN:
                    self._orders[i] = o.with_status(OrderStatus.CANCELLED)
                    return True
            return False

    def get_orderbook(self) -> list[Order]:
        with self._lock:
            return list(self._orders)

    def get_trade_book(self) -> list[Trade]:
        with self._lock:
            return list(self._trades)

    def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def _update_position(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        product_type: ProductType = ProductType.INTRADAY,
    ) -> dict[str, Position]:
        key = f"{symbol}:{exchange}"
        with self._lock:
            old_pos = self._positions.get(
                key, Position(symbol=symbol, exchange=exchange, product_type=product_type)
            )
            delta = quantity if side == Side.BUY else -quantity
            new_pos = old_pos.with_fill(delta, price)
            new_positions = dict(self._positions)
            new_positions[key] = new_pos
            return new_positions
