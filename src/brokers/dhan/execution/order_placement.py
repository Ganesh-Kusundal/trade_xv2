"""Order placement, slicing, and idempotency for the Dhan broker.

Extracted from :class:`brokers.dhan.execution.orders.OrdersAdapter` god class.
Owns:
- IdempotencyCache (thread-safe dedup by correlation_id)
- OrderPlacer (place_order, place_slice_order, payload building)
"""

from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal
from typing import Any

from domain.models.dtos import BrokerOrderPayload
from brokers.common.idempotency import IdempotencyCache
from brokers.dhan.exceptions import OrderError
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, DhanInstrumentRef
from brokers.dhan.resilience.invariants import assert_dhan_payload
from brokers.dhan.execution.order_validator import OrderValidator
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT, segment_to_exchange
from config.endpoints import Dhan
from domain import (
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    ProductType,
    Validity,
)
from domain import Side as OrderSide
from domain.field_mapping import DefaultFieldMapping
from domain.symbols import normalize_exchange
from domain.value_objects.price import to_wire_float
from domain.events import DomainEvent
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)

# Reusable field mapping instance for Dhan order parsing
_DHAN_MAPPING = DefaultFieldMapping()

# IdempotencyCache now lives in brokers.common.idempotency (shared with
# Upstox, built on infrastructure.idempotency.memory_cache — fixes a
# confirmed race condition that existed in the old Dhan-only version:
# get() used to read the cache without holding its lock, then delete an
# expired entry under a different lock, so two threads racing an expired
# read could both pass the check and the second del raised KeyError.
# Re-exported here so existing `from brokers.dhan.execution.order_placement
# import IdempotencyCache` call sites (and the two backward-compat shims at
# brokers/dhan/orders.py and brokers/dhan/order_placement.py) keep working.
__all__ = ["IdempotencyCache", "OrderPlacer"]


class OrderPlacer:
    """Handles order placement, slicing, and idempotent submission.

    Wires together validation, instrument resolution, risk checks, and
    the Dhan HTTP client into a single place_order / place_slice_order
    surface.  The idempotency protocol (reserve -> post -> commit) is
    encapsulated here together with :class:`IdempotencyCache`.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        identity: DhanIdentityProvider,
        idempotency: IdempotencyCache,
        validator: OrderValidator,
        risk_manager: RiskManagerPort | None = None,
        event_bus: EventBus | None = None,
        allow_live_orders: bool = False,
    ) -> None:
        self._client = client
        self._identity = identity
        self._idempotency = idempotency
        self._validator = validator
        self._risk_manager = risk_manager
        self._event_bus = event_bus
        self._allow_live_orders = allow_live_orders

    # -- Order placement ---------------------------------------------------

    def place_order(self, request: BrokerOrderPayload) -> OrderResponse:
        """Place a single order with idempotency and risk checks.

        Delegates payload building to :meth:`_build_order_payload` and
        response parsing to :meth:`_build_placed_order`. The idempotency
        cache is checked *before* any instrument resolution or API call
        so that a repeated call with the same *correlation_id* is nearly
        free.
        """
        cid = request.correlation_id or uuid.uuid4().hex
        cached = self._idempotency.get(cid)
        if cached is not None:
            logger.info("idempotency_cache_hit", extra={"correlation_id": cid})
            return cached

        if not self._idempotency.reserve(cid):
            # Another caller is placing with the same cid — wait for it.
            logger.info("idempotency_waiting", extra={"correlation_id": cid})
            for _ in range(50):
                cached = self._idempotency.get(cid)
                if cached is not None:
                    return cached
                time.sleep(0.1)
            return OrderResponse.fail("concurrent placement for same correlation_id timed out")

        try:
            return self._place_order_impl(request, cid)
        finally:
            # If we reserved but never committed (exception path), release
            # so the next caller can try rather than waiting for TTL expiry.
            # commit() already pops the reservation on success; this is a
            # harmless no-op in that case and the real release on the
            # exception path.
            self._idempotency.clear_reservation(cid)

    def _place_order_impl(self, request: BrokerOrderPayload, cid: str) -> OrderResponse:
        """Internal placement after idempotency reservation is held."""
        # -- Safety guard ---------------------------------------------------
        if not self._allow_live_orders:
            return OrderResponse.fail(
                "Live orders disabled; set DHAN_ALLOW_LIVE_ORDERS=1"
            )

        # -- Resolve instrument --------------------------------------------
        try:
            ref = self._identity.resolve_ref(request.symbol, request.exchange)
        except Exception as exc:
            return OrderResponse.fail(f"instrument_resolution_failed: {exc}")

        segment = ref.exchange_segment
        dhan_exchange = segment_to_exchange(segment)

        # -- Canonicalise enums --------------------------------------------
        ot, pt, vl = self._canonicalize_order_enums(request, dhan_exchange)

        # -- Pre-trade validation ------------------------------------------
        validation_errors = self._validator.validate_order(
            symbol=request.symbol,
            exchange=dhan_exchange.value if hasattr(dhan_exchange, "value") else str(dhan_exchange),
            quantity=request.quantity,
            order_type=ot,
            product_type=pt,
            price=request.price,
        )
        if validation_errors:
            return OrderResponse.fail("; ".join(validation_errors))

        # -- Risk check (domain RiskManagerPort.check_order) ---------------
        if self._risk_manager is not None:
            exchange_s = (
                dhan_exchange.value if hasattr(dhan_exchange, "value") else str(dhan_exchange)
            )
            side = request.transaction_type
            if not isinstance(side, OrderSide):
                side = OrderSide(str(side).upper())
            precheck = Order(
                order_id="risk-precheck",
                symbol=request.symbol,
                exchange=exchange_s,
                side=side,
                order_type=ot if isinstance(ot, OrderType) else OrderType.MARKET,
                quantity=int(request.quantity),
                price=request.price if request.price is not None else Decimal("0"),
                product_type=pt if isinstance(pt, ProductType) else ProductType.INTRADAY,
                status=OrderStatus.OPEN,
            )
            risk_result = self._risk_manager.check_order(precheck)
            allowed = bool(getattr(risk_result, "allowed", risk_result))
            if not allowed:
                reason = getattr(risk_result, "reason", None) or "risk_manager_rejected"
                return OrderResponse.fail(f"Risk check failed: {reason}")

        # -- Build & send payload ------------------------------------------
        payload = self._build_order_payload(ref, request, ot, pt, vl, cid)
        assert_dhan_payload(payload, context="orders.place_order")

        try:
            data = self._client.post("/orders", json=payload)
        except Exception as exc:
            return OrderResponse.fail(f"order_placement_error: {exc}")

        # -- Parse response ------------------------------------------------
        placed = self._build_placed_order(data, ref, request, cid)
        if placed.success:
            self._idempotency.commit(cid, placed)
            self._publish(placed, request)
        return placed

    def place_slice_order(
        self,
        symbol: str,
        exchange: str,
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ) -> OrderResponse:
        """Place a sliced order via the Dhan slicing endpoint.

        Slicing splits a large order into smaller lots for better execution.
        The Dhan API handles the slicing server-side.
        """
        if not self._allow_live_orders:
            return OrderResponse.fail(
                "Live orders disabled; set DHAN_ALLOW_LIVE_ORDERS=1"
            )

        try:
            ref = self._identity.resolve_ref(symbol, exchange)
        except Exception as exc:
            return OrderResponse.fail(f"instrument_resolution_failed: {exc}")

        segment = ref.exchange_segment
        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "transactionType": side.upper(),
            "quantity": quantity,
            "orderType": order_type.upper(),
            "productType": product_type.upper(),
        }

        if price is not None and price > 0:
            payload["price"] = str(price)

        assert_dhan_payload(payload, context="orders.place_slice_order")

        try:
            data = self._client.post("/orders/slicing", json=payload)
        except Exception as exc:
            return OrderResponse.fail(f"slice_order_error: {exc}")

        raw = data.get("data", data) if isinstance(data, dict) else data
        order_id = (
            str(raw.get("orderId", raw.get("order_id", "")))
            if isinstance(raw, dict)
            else str(raw)
        )
        success = bool(order_id) and order_id != "0"
        response = OrderResponse(
            success=success,
            order_id=order_id,
            broker_order_id=order_id,
            message="Slice order placed successfully" if success else "Slice order failed",
            status=OrderStatus.OPEN if success else OrderStatus.REJECTED,
        )
        if success:
            self._publish_slice(response, symbol, exchange, side, quantity, order_type, product_type)
        return response

    def _publish_slice(
        self,
        response: OrderResponse,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        order_type: str,
        product_type: str,
    ) -> None:
        if self._event_bus is None:
            return
        try:
            order = Order(
                order_id=response.order_id,
                symbol=symbol,
                exchange=exchange,
                side=OrderSide(side.upper()),
                order_type=OrderType(order_type.upper()),
                quantity=int(quantity),
                product_type=ProductType(product_type.upper()),
                status=response.status,
            )
            self._event_bus.publish(DomainEvent.now("ORDER_PLACED", {"order": order}))
        except Exception:
            logger.exception("event_publish_failed")

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _canonicalize_order_enums(request, dhan_exchange):
        """Normalise order type / product type / validity to Dhan wire values."""
        ot = (
            request.order_type.value
            if isinstance(request.order_type, OrderType)
            else str(request.order_type).upper()
        )
        pt = (
            request.product_type.value
            if isinstance(request.product_type, ProductType)
            else str(request.product_type).upper()
        )
        vl = (
            request.validity.value
            if hasattr(request, "validity") and isinstance(getattr(request, "validity", None), Validity)
            else "DAY"
        )
        return ot, pt, vl

    def _build_order_payload(self, ref, request, ot, pt, vl, cid) -> dict:
        segment = ref.exchange_segment
        payload: dict[str, Any] = {
            "dhanClientId": self._client.client_id,
            "correlationId": cid,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "transactionType": (
                request.transaction_type.value
                if hasattr(request.transaction_type, "value")
                else str(request.transaction_type).upper()
            ),
            "quantity": int(request.quantity),
            "orderType": ot,
            "productType": pt,
            "validity": vl,
        }
        # Dhan /orders expects numeric float for price/triggerPrice (matches the
        # official dhanhq SDK, _order.py: `"price": float(price)`), and is the
        # same canonical wire helper Dhan super/forever/margin orders already use.
        if request.price is not None and request.price > 0:
            payload["price"] = to_wire_float(request.price)
        else:
            payload["price"] = 0.0
        if request.trigger_price is not None and request.trigger_price > 0:
            payload["triggerPrice"] = to_wire_float(request.trigger_price)
        if request.disclosed_quantity is not None and request.disclosed_quantity > 0:
            payload["disclosedQuantity"] = int(request.disclosed_quantity)
        return payload

    @staticmethod
    def _build_placed_order(data, ref, request, cid) -> OrderResponse:
        raw = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(raw, dict):
            order_id = str(raw.get("orderId", raw.get("order_id", "")))
            broker_id = str(raw.get("orderId", raw.get("order_id", "")))
            status_str = str(raw.get("orderStatus", raw.get("status", ""))).upper()
            # Delegates to the canonical, registered status mapper
            # (domain.status_mapper.COMMON_STATUS_MAP + DHAN_STATUS_MAP)
            # instead of a hand-rolled dict. The previous hand-rolled dict
            # referenced OrderStatus.PENDING, which does not exist on the
            # canonical enum (OPEN/PARTIALLY_FILLED/FILLED/CANCELLED/
            # PARTIALLY_CANCELLED/REJECTED/EXPIRED/UNKNOWN) -- every Dhan
            # place_order call raised AttributeError here.
            status = OrderStatus.normalize(status_str) if status_str else OrderStatus.OPEN
            err = raw.get("errorMessage") or raw.get("error", "")
            if err:
                return OrderResponse.fail(
                    message=str(err),
                    error_code=str(raw.get("errorCode", "")),
                    status=OrderStatus.REJECTED,
                )
        else:
            order_id = str(raw) if raw else ""
            broker_id = order_id
            status = OrderStatus.OPEN

        return OrderResponse(
            success=bool(order_id),
            order_id=order_id,
            broker_order_id=broker_id,
            correlation_id=cid,
            message="Order placed" if order_id else "Order placement failed",
            status=status,
        )

    def _publish(self, response: OrderResponse, request: BrokerOrderPayload) -> None:
        if self._event_bus is None:
            return
        try:
            order = Order(
                order_id=response.order_id,
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.transaction_type,
                order_type=request.order_type,
                quantity=int(request.quantity),
                price=request.price or Decimal("0"),
                product_type=request.product_type,
                status=response.status,
                correlation_id=response.correlation_id,
            )
            self._event_bus.publish(DomainEvent.now("ORDER_PLACED", {"order": order}))
        except Exception:
            logger.exception("event_publish_failed")
