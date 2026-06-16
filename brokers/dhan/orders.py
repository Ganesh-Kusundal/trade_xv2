"""Orders adapter — place, modify, cancel, orderbook, tradebook.

Production-hardened with:
- Pre-trade validation (lot size, product type, quantity, price)
- Idempotency cache (prevents duplicate orders on retry)
- Structured logging (full audit trail)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from brokers.common.event_bus import DomainEvent, EventBus
from brokers.common.oms.risk_manager import RiskManager
from brokers.dhan.domain import (
    Exchange,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    Trade,
    Validity,
)
from brokers.dhan.exceptions import OrderError
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)

# Segments where only INTRADAY and MARGIN product types are allowed
_DERIVATIVE_SEGMENTS = frozenset({
    "NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CURRENCY", "BSE_CURRENCY",
})

# Product types NOT allowed for derivatives
_EQUITY_ONLY_PRODUCTS = frozenset({"CNC", "MTF"})


class IdempotencyCache:
    """Prevents duplicate order placement by caching responses keyed on correlation_id.

    Thread-safe: all cache mutations and lookups are guarded by a reentrant lock.
    The ``lock`` context manager can be used to build larger atomic critical
    sections (e.g. check-then-act order placement).
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[float, Order]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.RLock()

    @contextmanager
    def lock(self, _key: str):
        """Acquire the cache lock for an atomic check-then-act sequence."""
        with self._lock:
            yield self

    def get(self, key: str) -> Order | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, order = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                return None
            return order

    def put(self, key: str, order: Order) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), order)


class OrdersAdapter:
    def __init__(
        self,
        client: DhanHttpClient,
        resolver: SymbolResolver,
        idempotency_cache: IdempotencyCache | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
    ):
        self._client = client
        self._resolver = resolver
        self._idempotency = idempotency_cache or IdempotencyCache()
        self._event_bus = event_bus
        self._risk_manager = risk_manager

    # ── Validation ────────────────────────────────────────────────────

    def validate_order(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        order_type: str | OrderType,
        product_type: str | ProductType,
        price: Decimal | None = None,
    ) -> list[str]:
        """Validate an order before submission. Returns list of error strings (empty = valid)."""
        errors: list[str] = []

        if quantity <= 0:
            errors.append(f"Quantity must be positive, got {quantity}")

        ot_val = order_type.value if isinstance(order_type, OrderType) else str(order_type).upper()
        pt_val = product_type.value if isinstance(product_type, ProductType) else str(product_type).upper()

        if ot_val in ("LIMIT", "STOP_LOSS") and (price is None or price <= 0):
            errors.append(f"LIMIT/SL orders require price > 0, got {price}")

        # Resolve instrument for lot size and segment checks
        try:
            inst = self._resolver.resolve(symbol, exchange)
        except Exception:
            errors.append(f"Instrument not found: {symbol} on {exchange}")
            return errors

        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")

        # Lot size check for derivatives
        if segment in _DERIVATIVE_SEGMENTS and inst.lot_size > 1:
            if quantity % inst.lot_size != 0:
                errors.append(
                    f"Quantity {quantity} is not a multiple of lot size {inst.lot_size} "
                    f"for {symbol} on {inst.exchange.value}"
                )

        # Product type × segment check
        if segment in _DERIVATIVE_SEGMENTS and pt_val in _EQUITY_ONLY_PRODUCTS:
            errors.append(
                f"Product type {pt_val} is not valid for {segment}. "
                f"Use INTRADAY or MARGIN for derivatives."
            )

        return errors

    def validate_order_warnings(
        self,
        quantity: int,
        price: Decimal | None = None,
    ) -> list[str]:
        """Return non-blocking warnings. High notional is the main check."""
        warnings: list[str] = []
        if price and price > 0:
            notional = Decimal(str(quantity)) * price
            if notional > Decimal("50000"):
                warnings.append(f"High notional: ₹{notional:,.0f} exceeds ₹50,000 threshold")
        return warnings

    # ── Order lifecycle ───────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | OrderSide = "BUY",
        quantity: int = 0,
        order_type: str | OrderType = "MARKET",
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        product_type: str | ProductType = "INTRADAY",
        validity: str | Validity = "DAY",
        correlation_id: str | None = None,
    ) -> Order:
        # Always generate a correlation id so every placement is idempotent.
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Atomic check-then-act: one and only one thread posts for this id.
        with self._idempotency.lock(correlation_id):
            cached = self._idempotency.get(correlation_id)
            if cached is not None:
                logger.info("idempotency_hit", extra={"correlation_id": correlation_id, "order_id": cached.order_id})
                return cached

            # Validation
            errors = self.validate_order(symbol, exchange, quantity, order_type, product_type, price)
            if errors:
                msg = "; ".join(errors)
                logger.warning("order_validation_failed", extra={"symbol": symbol, "errors": errors})
                raise OrderError(f"Order validation failed: {msg}")

            warnings = self.validate_order_warnings(quantity, price)
            for w in warnings:
                logger.warning("order_warning", extra={"symbol": symbol, "warning": w})

            # Resolve instrument and canonicalise enums once for risk + payload.
            inst = self._resolver.resolve(symbol, exchange)
            segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")
            side_val = side.value if isinstance(side, OrderSide) else str(side).upper()
            ot_val = order_type.value if isinstance(order_type, OrderType) else str(order_type).upper()
            pt_val = product_type.value if isinstance(product_type, ProductType) else str(product_type).upper()
            v_val = validity.value if isinstance(validity, Validity) else str(validity).upper()

            # Pre-trade risk check
            if self._risk_manager is not None:
                preview = Order(
                    order_id="",
                    symbol=symbol,
                    exchange=inst.exchange.value,
                    side=OrderSide(side_val),
                    order_type=OrderType(ot_val),
                    quantity=quantity,
                    price=price if price and price > 0 else Decimal("0"),
                    trigger_price=trigger_price if trigger_price and trigger_price > 0 else Decimal("0"),
                    product_type=ProductType(pt_val),
                    validity=Validity(v_val),
                )
                risk_result = self._risk_manager.check_order(preview)
                if not risk_result.allowed:
                    raise OrderError(f"Risk check failed: {risk_result.reason}")

            payload: dict[str, Any] = {
                "dhanClientId": self._client.client_id,
                "securityId": inst.security_id,
                "exchangeSegment": segment,
                "transactionType": side_val,
                "orderType": ot_val,
                "productType": pt_val,
                "validity": v_val,
                "quantity": quantity,
                "correlationId": correlation_id,
            }
            if price and price > 0:
                payload["price"] = float(price)
            if trigger_price and trigger_price > 0:
                payload["triggerPrice"] = float(trigger_price)

            data = self._client.post("/orders", json=payload)
            order_id = str(data.get("data", {}).get("orderId") or data.get("orderId") or "")

            order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=inst.exchange,
                side=OrderSide(side_val),
                order_type=OrderType(ot_val),
                quantity=quantity,
                status=OrderStatus.OPEN,
                price=price if price and price > 0 else Decimal("0"),
                trigger_price=trigger_price if trigger_price and trigger_price > 0 else Decimal("0"),
                product_type=ProductType(pt_val),
                validity=Validity(v_val),
                correlation_id=correlation_id,
            )

            logger.info("order_placed", extra={
                "order_id": order_id, "symbol": symbol, "side": side_val,
                "quantity": quantity, "order_type": ot_val, "price": str(price or 0),
                "product_type": pt_val, "exchange": inst.exchange.value,
            })

            self._idempotency.put(correlation_id, order)
            self._publish("ORDER_PLACED", order)
            return order

    def modify_order(self, order_id: str, **changes: Any) -> Order:
        payload = {k: v for k, v in changes.items() if v is not None}
        self._client.put(f"/orders/{order_id}", json=payload)
        logger.info("order_modified", extra={"order_id": order_id, "changes": list(changes.keys())})
        return Order(
            order_id=order_id,
            symbol="",
            exchange="NSE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
            status=OrderStatus.OPEN,
        )

    def cancel_order(self, order_id: str) -> bool:
        data = self._client.delete(f"/orders/{order_id}")
        success = isinstance(data, dict)
        logger.info("order_cancelled", extra={"order_id": order_id, "success": success})
        return success

    def cancel_all_orders(self) -> list[tuple[str, bool]]:
        data = self._client.delete("/orders")
        items = data.get("data", []) if isinstance(data, dict) else []
        result = [(str(i.get("orderId", i)), True) for i in (items if isinstance(items, list) else [])]
        logger.info("all_orders_cancelled", extra={"count": len(result)})
        return result

    def get_order(self, order_id: str) -> Order:
        data = self._client.get(f"/orders/{order_id}")
        raw = data.get("data", data) if isinstance(data, dict) else data
        return self._parse_order(raw if isinstance(raw, dict) else {})

    def get_orderbook(self) -> list[Order]:
        data = self._client.get("/orders")
        items = data.get("data", []) if isinstance(data, dict) else []
        orders = [self._parse_order(i) for i in (items if isinstance(items, list) else [])]
        logger.info("orderbook_fetched", extra={"count": len(orders)})
        return orders

    def get_trade_book(self) -> list[Trade]:
        data = self._client.get("/trades")
        items = data.get("data", []) if isinstance(data, dict) else []
        trades = []
        for item in (items if isinstance(items, list) else []):
            trades.append(Trade(
                trade_id=str(item.get("tradeId", "")),
                order_id=str(item.get("orderId", "")),
                symbol=str(item.get("tradingSymbol", "")),
                exchange=_parse_exchange(item.get("exchangeSegment", "NSE_EQ")),
                side=OrderSide.BUY if item.get("transactionType") == "BUY" else OrderSide.SELL,
                quantity=int(item.get("tradedQty", 0)),
                price=Decimal(str(item.get("tradedPrice", 0))),
            ))
        logger.info("tradebook_fetched", extra={"count": len(trades)})
        return trades

    def get_order_status(self, order_id: str) -> OrderStatus:
        order = self.get_order(order_id)
        return order.status

    def kill_switch(self, enable: bool) -> bool:
        action = "ACTIVATE" if enable else "DEACTIVATE"
        data = self._client.post(f"/killswitch?killSwitchStatus={action}", json={})
        success = isinstance(data, dict) and data.get("status", "").lower() == "success"
        logger.info("kill_switch", extra={"action": action, "success": success})
        return success

    def _publish(self, event_type: str, order: Order) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                {"order": order},
                symbol=order.symbol,
                source="DhanOrdersAdapter",
            )
        )

    @staticmethod
    def _parse_order(raw: dict) -> Order:
        return Order.from_broker_dict(raw, exchange_resolver=_parse_exchange)


def _parse_exchange(seg: str) -> Exchange:
    from brokers.dhan.segments import SEGMENT_TO_EXCHANGE
    exch = SEGMENT_TO_EXCHANGE.get(str(seg), "NSE")
    return Exchange(exch)


def _opt_dec(val) -> Decimal | None:
    if val in (None, ""):
        return None
    return Decimal(str(val))
