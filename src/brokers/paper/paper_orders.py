"""Simulated order management for paper trading."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from domain import (
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Side,
    Trade,
    Validity,
)
from domain.orders.intent import OrderIntent
from domain.symbols import normalize_exchange, normalize_symbol

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
        risk = self._order_manager.risk_manager
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

        # REF-018: Route through OMS OrderManager for idempotency when available.
        if self._order_manager is not None:
            return self._place_via_oms(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=price,
                order_type=order_type,
                product_type=product_type,
                validity=validity,
                trigger_price=trigger_price,
                correlation_id=correlation_id,
            )

        # Legacy path: no OMS available, manage state internally.
        return self._place_internal(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

    def _place_via_oms(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        order_type: OrderType,
        product_type: ProductType,
        validity: Validity,
        trigger_price: Decimal,
        correlation_id: str | None,
    ) -> Order:
        """Route through OrderManager.place_order for idempotency + risk + events.

        Builds a domain :class:`OrderIntent` (not application ``OmsOrderCommand``)
        so brokers never import the application layer. OrderManager only needs
        duck-typed attributes (symbol/side/qty/…); OrderIntent matches that shape.
        """
        self._order_seq += 1
        seq = self._order_seq

        cmd = OrderIntent(
            symbol=normalize_symbol(symbol),
            exchange=normalize_exchange(exchange),
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            correlation_id=correlation_id or f"ppr:{seq}",
        )

        fill_price = (
            price
            if price > 0 and order_type == OrderType.LIMIT
            else self._md.get_ltp(symbol, exchange)
        )
        is_market = order_type == OrderType.MARKET

        def _fill(cmd: OrderIntent) -> Order:
            if is_market:
                return Order(
                    order_id=f"PPR-{seq:06d}",
                    symbol=cmd.symbol,
                    exchange=cmd.exchange,
                    side=cmd.side,
                    order_type=cmd.order_type,
                    quantity=cmd.quantity,
                    filled_quantity=cmd.quantity,
                    price=cmd.price,
                    trigger_price=trigger_price,
                    status=OrderStatus.FILLED,
                    timestamp=datetime.now(timezone.utc),
                    product_type=cmd.product_type,
                    avg_price=fill_price,
                    correlation_id=cmd.correlation_id,
                )
            # Resting limit — OPEN
            return Order(
                order_id=f"PPR-{seq:06d}",
                symbol=cmd.symbol,
                exchange=cmd.exchange,
                side=cmd.side,
                order_type=cmd.order_type,
                quantity=cmd.quantity,
                filled_quantity=0,
                price=cmd.price,
                trigger_price=trigger_price,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(timezone.utc),
                product_type=cmd.product_type,
                avg_price=Decimal("0"),
                correlation_id=cmd.correlation_id,
            )

        result = self._order_manager.place_order(
            request=cmd,
            submit_fn=_fill,
        )
        if not result.success or result.order is None:
            rejected = Order(
                order_id=f"PPR-{seq:06d}",
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.REJECTED,
                correlation_id=correlation_id,
            )
            with self._lock:
                self._orders.append(rejected)
            # Upsert rejected order to OMS for audit trail (matches legacy behavior).
            self._order_manager.upsert_order(rejected)
            return rejected

        # Keep internal order/trade list synced for backward-compatible getters.
        with self._lock:
            self._orders.append(result.order)
            self._order_seq = seq  # sync sequence counter

        # Only record trade / positions on market fills
        if is_market and result.order.status == OrderStatus.FILLED:
            self._trade_seq += 1
            trade = Trade(
                trade_id=f"PPR-T-{self._trade_seq:06d}",
                order_id=result.order.order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=fill_price,
                trade_value=fill_price * quantity,
                timestamp=datetime.now(timezone.utc),
                product_type=product_type,
            )
            with self._lock:
                self._trades.append(trade)
                self._positions = self._update_position(
                    symbol,
                    exchange,
                    side,
                    quantity,
                    fill_price,
                    product_type,
                )
            self._order_manager.record_trade(trade)

        return result.order

    def _place_internal(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        order_type: OrderType,
        product_type: ProductType,
        validity: Validity,
        trigger_price: Decimal,
        correlation_id: str | None,
    ) -> Order:
        """Legacy internal order placement (no OMS, backward compatible).

        MARKET → instant fill (FILLED).
        LIMIT / stop styles → rest as OPEN (so cancel/modify e2e works).
        """
        from brokers.common.order_validation import validate_lot_size

        # Paper default lot size 1; still route through shared validator.
        lot_err = validate_lot_size(quantity, 1, symbol, exchange)
        if lot_err:
            raise ValueError(lot_err)

        is_market = order_type == OrderType.MARKET
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
                return rejected

            if is_market:
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

                if self._position_manager is not None:
                    self._position_manager.apply_trade(trade)
                self._positions = self._update_position(
                    symbol, exchange, side, quantity, fill_price, product_type
                )
                return order

            # Resting limit / conditional — OPEN (no fill yet)
            order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                filled_quantity=0,
                price=price,
                trigger_price=trigger_price,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(timezone.utc),
                product_type=product_type,
                validity=validity,
                avg_price=Decimal("0"),
                correlation_id=correlation_id,
            )
            self._orders.append(order)
            return order

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            for i, o in enumerate(self._orders):
                if o.order_id == order_id and o.status == OrderStatus.OPEN:
                    self._orders[i] = o.with_status(OrderStatus.CANCELLED)
                    return True
            return False

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID.

        H1 Critical Fix: Enables post-cancellation verification for paper
        trading by allowing lookup of individual orders.

        Args:
            order_id: Paper order ID to look up

        Returns:
            Order if found, None if not in orderbook
        """
        with self._lock:
            for order in self._orders:
                if order.order_id == order_id:
                    return order
        return None

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        trigger_price: Decimal | None = None,
        validity: Validity | None = None,
    ) -> Order:
        """Modify an open order - simulates order modification.

        P-2.1 Critical Fix: Implements modify_order for paper trading.
        Only allows modification if order is in OPEN status.
        Changes are applied to the order and a new modified order is created.

        Args:
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            order_type: New order type (optional)
            trigger_price: New trigger price for SL orders (optional)
            validity: New validity (optional)

        Returns:
            Modified Order with updated fields

        Raises:
            ValueError: If order not found or not in OPEN status
        """
        with self._lock:
            # Find the order
            original_idx = None
            original_order = None
            for i, o in enumerate(self._orders):
                if o.order_id == order_id:
                    original_idx = i
                    original_order = o
                    break

            if original_order is None:
                raise ValueError(f"Order {order_id} not found")

            if original_order.status != OrderStatus.OPEN:
                raise ValueError(
                    f"Cannot modify order {order_id} with status {original_order.status.value}. "
                    f"Only OPEN orders can be modified."
                )

            # In-place modify (same order_id) — matches OMS/broker modify semantics
            modified_order = Order(
                order_id=original_order.order_id,
                symbol=original_order.symbol,
                exchange=original_order.exchange,
                side=original_order.side,
                order_type=order_type if order_type is not None else original_order.order_type,
                quantity=quantity if quantity is not None else original_order.quantity,
                price=price if price is not None else original_order.price,
                trigger_price=trigger_price if trigger_price is not None else original_order.trigger_price,
                validity=validity if validity is not None else original_order.validity,
                product_type=original_order.product_type,
                correlation_id=original_order.correlation_id,
                status=OrderStatus.OPEN,
                filled_quantity=original_order.filled_quantity,
                timestamp=datetime.now(timezone.utc),
            )

            # Risk check on modified order
            allowed, reason = self._risk_check(modified_order)
            if not allowed:
                # Leave original OPEN; report rejection via exception for EP wrap
                raise ValueError(reason or "Risk check failed on modification")

            self._orders[original_idx] = modified_order
            return modified_order

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
