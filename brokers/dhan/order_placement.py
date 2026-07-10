"""Order placement, slicing, and idempotency for the Dhan broker.

Extracted from :class:`brokers.dhan.orders.OrdersAdapter` god class.
Owns:
- IdempotencyCache (thread-safe dedup by correlation_id)
- OrderPlacer (place_order, place_slice_order, payload building)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from tradex.runtime.dtos import BrokerOrderPayload
from brokers.dhan.exceptions import OrderError
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, DhanInstrumentRef
from brokers.dhan.invariants import assert_dhan_payload
from brokers.dhan.order_validator import OrderValidator
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
from domain.events import DomainEvent
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)

# Reusable field mapping instance for Dhan order parsing
_DHAN_MAPPING = DefaultFieldMapping()


class IdempotencyCache:
    """Prevents duplicate order placement by caching responses keyed on correlation_id.

    Thread-safe: all cache mutations and lookups are guarded by a reentrant lock.
    The ``lock`` context manager can be used to build larger atomic critical
    sections (e.g. check-then-act order placement).
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[float, OrderResponse]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        # Per-key reservation events. A live event means a thread is currently
        # performing the blocking HTTP post for that correlation id; concurrent
        # callers with the same id wait on it instead of re-submitting.
        self._reservations: dict[str, threading.Event] = {}

    @contextmanager
    def lock(self, _key: str):
        """Acquire the cache lock for an atomic check-then-act sequence."""
        with self._lock:
            yield self

    def get(self, key: str) -> OrderResponse | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, response = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                return None
            return response

    def put(self, key: str, response: OrderResponse) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), response)

    def reserve(self, key: str) -> tuple[str, OrderResponse | None, threading.Event | None]:
        """Atomically check-and-reserve a correlation id under the lock.

        Returns one of:

        * ``("hit", response, None)`` — the id was already successfully
          posted; the caller should return ``response`` without posting.
        * ``("in_progress", None, event)`` — another thread is currently
          posting for this id; the caller should wait on ``event`` and then
          re-check (it will eventually observe a ``"hit"``).
        * ``("reserved", None, event)`` — this thread now owns the post; the
          caller may release the lock and perform the blocking HTTP call,
          then call :meth:`commit` (or :meth:`clear_reservation` on failure).
        """
        with self._lock:
            cached = self.get(key)
            if cached is not None:
                return ("hit", cached, None)
            event = self._reservations.get(key)
            if event is not None:
                return ("in_progress", None, event)
            event = threading.Event()
            self._reservations[key] = event
            return ("reserved", None, event)

    def commit(self, key: str, response: OrderResponse) -> None:
        """Record a successful outcome and wake any waiters for this id."""
        with self._lock:
            self.put(key, response)
            event = self._reservations.pop(key, None)
            if event is not None:
                event.set()

    def clear_reservation(self, key: str) -> None:
        """Release a reservation without recording an outcome.

        Used when the post fails (or pre-flight validation fails) so that a
        later retry with the same correlation id is allowed to submit.
        Any waiter is woken so it can re-check and retry.
        """
        with self._lock:
            event = self._reservations.pop(key, None)
            if event is not None:
                event.set()


class OrderPlacer:
    """Handles order placement, slicing, and idempotent submission.

    Wires together validation, instrument resolution, risk checks, and
    the Dhan HTTP client into a single place_order / place_slice_order
    surface.  The idempotency protocol (reserve → post → commit) is
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

    # ── Order placement ──────────────────────────────────────────────────

    def place_order(self, request: BrokerOrderPayload) -> OrderResponse:
        """Place an order via the Dhan API.

        Args:
            request: :class:`BrokerOrderPayload` with canonical order fields
                     plus broker-transport metadata (exchange_segment,
                     transport_only, etc.).

        Returns:
            :class:`OrderResponse` with success/failure status.

        .. note::
            **Exception policy** (B6 normalized): returns ``OrderResponse.fail()``
            on validation/risk failures, matching
            :class:`~brokers.upstox.orders.order_command_adapter.UpstoxOrderCommandAdapter`.
        """
        if not self._allow_live_orders:
            return OrderResponse.fail("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        correlation_id = request.correlation_id
        symbol = request.symbol or ""
        exchange = request.exchange or "NSE"
        side = request.transaction_type
        quantity = request.quantity
        order_type = request.order_type
        price = request.price
        trigger_price = request.trigger_price
        product_type = request.product_type
        validity = request.validity

        # Always generate a correlation id so every placement is idempotent.
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Check-reserve / commit idempotency protocol.
        #
        # The idempotency lock is held ONLY for the cache check-and-reserve and
        # for the final result commit. The blocking HTTP post to /orders happens
        # WITHOUT the lock held, so concurrent placements with *different*
        # correlation ids are no longer serialized behind one another (previously
        # a single hung broker call stalled every placement on the adapter).
        #
        # Same-correlation-id callers that arrive while a post is in flight wait
        # on a per-id reservation event instead of re-submitting, preserving the
        # "no double submit" guarantee.
        while True:
            status, cached, in_flight = self._idempotency.reserve(correlation_id)
            if status == "hit":
                logger.info(
                    "idempotency_hit",
                    extra={"correlation_id": correlation_id, "order_id": cached.order_id},
                )
                return cached
            if status == "in_progress":
                # Another thread owns the in-flight post for this id; wait for it.
                in_flight.wait(timeout=30)
                continue
            # status == "reserved": this thread owns the post. Proceed.
            break

        # ── Pre-flight (OUTSIDE the idempotency lock) ──────────────────

        # Validation
        errors = self._validator.validate_order(
            symbol, exchange, quantity, order_type, product_type, price
        )
        if errors:
            msg = "; ".join(errors)
            logger.warning(
                "order_validation_failed", extra={"symbol": symbol, "errors": errors}
            )
            self._idempotency.clear_reservation(correlation_id)
            return OrderResponse.fail(f"Order validation failed: {msg}")

        warnings = self._validator.validate_order_warnings(quantity, price)
        for w in warnings:
            logger.warning("order_warning", extra={"symbol": symbol, "warning": w})

        # Resolve instrument via the identity provider so the carrier
        # (DhanInstrumentRef) is the only thing that can flow into
        # the payload builder. The provider enforces the Dhan-only
        # contract; any non-Dhan segment or non-digit security_id
        # raises DhanIdentityError before we ever call _client.post.
        # The expected_segment hint maps the user-supplied exchange
        # string to a Dhan segment so the index-fallback is rejected
        # for derivatives queries (PR-C.4).
        try:
            ref = self._identity.resolve_ref(
                symbol,
                exchange,
                expected_segment=EXCHANGE_TO_SEGMENT.get(normalize_exchange(exchange)),
            )
        except Exception as exc:
            self._idempotency.clear_reservation(correlation_id)
            return OrderResponse.fail(f"Instrument resolution failed: {exc}")

        segment = ref.exchange_segment
        side_val, ot_val, pt_val, v_val = self._canonicalize_order_enums(
            side,
            order_type,
            product_type,
            validity,
        )

        # Pre-trade risk check is always enforced at the broker boundary.
        if self._risk_manager is not None:
            preview = Order(
                order_id="",
                symbol=symbol,
                exchange=ref.exchange.value,
                side=OrderSide(side_val),
                order_type=OrderType(ot_val),
                quantity=quantity,
                price=price if price and price > 0 else Decimal("0"),
                trigger_price=trigger_price
                if trigger_price and trigger_price > 0
                else Decimal("0"),
                product_type=ProductType(pt_val),
                validity=Validity(v_val),
            )
            risk_result = self._risk_manager.check_order(preview)
            if not risk_result.allowed:
                self._idempotency.clear_reservation(correlation_id)
                return OrderResponse.fail(f"Risk check failed: {risk_result.reason}")

        payload = self._build_order_payload(
            ref,
            segment,
            side_val,
            ot_val,
            pt_val,
            v_val,
            quantity,
            price,
            trigger_price,
            correlation_id,
        )
        # PR-B: defence-in-depth. The carrier already enforced the
        # Dhan-internal contract, but a future change could build a
        # payload from non-carrier sources. Re-verify at the boundary.
        assert_dhan_payload(payload, context="orders.place_order")

        # ── Blocking broker call (NO idempotency lock held) ────────────
        try:
            data = self._client.post("/orders", json=payload)
        except Exception as exc:
            # Release the reservation so a later retry with the same id is
            # allowed to submit.
            self._idempotency.clear_reservation(correlation_id)
            return OrderResponse.fail(f"Broker API error: {exc}")

        order = self._build_placed_order(
            data,
            symbol,
            ref.exchange,
            side_val,
            ot_val,
            pt_val,
            v_val,
            quantity,
            price,
            trigger_price,
            correlation_id,
        )

        logger.info(
            "order_placed",
            extra={
                "order_id": order.order_id,
                "symbol": symbol,
                "side": side_val,
                "quantity": quantity,
                "order_type": ot_val,
                "price": str(price or 0),
                "product_type": pt_val,
                "exchange": ref.exchange.value,
            },
        )

        response = OrderResponse(
            success=True,
            order_id=order.order_id,
            broker_order_id=order.order_id,
            status=order.status,
            message="Order placed successfully",
        )
        # Commit under the lock: record the outcome and wake any waiters.
        self._idempotency.commit(correlation_id, response)
        self._publish("ORDER_PLACED", order)
        return response

    # ── Slice orders ────────────────────────────────────────────────────

    def place_slice_order(self, symbol: str, exchange: str, **kwargs) -> OrderResponse:
        """Place a slice order (automatically splits large orders).

        Uses POST /orders/slicing endpoint instead of POST /orders.
        Same payload structure as regular place_order.

        Returns:
            :class:`OrderResponse` with success/failure status.
        """
        # Safety guard: prevent live slice orders if disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        side = kwargs.get("side", "BUY")
        quantity: int = kwargs["quantity"]
        order_type = kwargs.get("order_type", "MARKET")
        product_type = kwargs.get("product_type", "INTRADAY")
        price: Decimal = kwargs.get("price", Decimal("0"))
        trigger_price: Decimal = kwargs.get("trigger_price", Decimal("0"))
        validity = kwargs.get("validity", "DAY")
        correlation_id: str | None = kwargs.get("correlation_id")

        # Resolve instrument via the identity provider so the carrier
        # (DhanInstrumentRef) is the only thing that can flow into
        # the payload builder. Slice orders are broker-managed and have
        # no idempotency/risk check; the identity provider is the
        # single place that enforces the Dhan-internal contract.
        ref = self._identity.resolve_ref(symbol, exchange)
        segment = ref.exchange_segment
        side_val, ot_val, pt_val, v_val = self._canonicalize_order_enums(
            side,
            order_type,
            product_type,
            validity,
        )

        # Pre-trade validation (no idempotency/risk — slice orders are broker-managed).
        self._validator.validate_order(
            symbol=symbol,
            exchange=exchange,
            quantity=quantity,
            order_type=ot_val,
            product_type=pt_val,
            price=price if price > 0 else None,
        )

        payload = self._build_order_payload(
            ref,
            segment,
            side_val,
            ot_val,
            pt_val,
            v_val,
            quantity,
            price,
            trigger_price,
            correlation_id,
        )
        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="orders.place_slice_order")

        data = self._client.post(Dhan.SLICE_ORDER, json=payload)
        order_data = data.get("data", data)
        order = Order.from_broker_dict(
            order_data,
            field_mapping=_DHAN_MAPPING,
            exchange_resolver=segment_to_exchange,
        )

        logger.info(
            "slice_order_placed",
            extra={
                "order_id": order.order_id,
                "symbol": symbol,
                "exchange": exchange,
                "side": side_val,
                "quantity": quantity,
            },
        )

        self._publish("ORDER_PLACED", order)
        return OrderResponse(
            success=True,
            order_id=order.order_id,
            broker_order_id=order.order_id,
            status=order.status,
            message="Slice order placed successfully",
        )

    # ── Shared helpers ──────────────────────────────────────────────────

    @staticmethod
    def _canonicalize_order_enums(
        side: str | OrderSide,
        order_type: str | OrderType,
        product_type: str | ProductType,
        validity: str | Validity,
    ) -> tuple[str, str, str, str]:
        """Canonicalize order enum/mixed values to uppercase strings."""
        sv = side.value if isinstance(side, OrderSide) else str(side).upper()
        ot = order_type.value if isinstance(order_type, OrderType) else str(order_type).upper()
        pt = (
            product_type.value
            if isinstance(product_type, ProductType)
            else str(product_type).upper()
        )
        vl = validity.value if isinstance(validity, Validity) else str(validity).upper()
        return sv, ot, pt, vl

    def _build_order_payload(
        self,
        ref: DhanInstrumentRef,
        segment: str,
        side_val: str,
        ot_val: str,
        pt_val: str,
        v_val: str,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Build the Dhan order placement payload dict.

        The *ref* argument is a :class:`DhanInstrumentRef`; the carrier
        is the only thing that can flow into a Dhan HTTP body, and
        ``DhanInstrumentRef.__post_init__`` has already enforced the
        Dhan-internal contract (segment ∈ Dhan's set, security_id is
        a positive digit string).
        """
        payload: dict[str, Any] = {
            "dhanClientId": self._client.client_id,
            "securityId": ref.security_id_str(),
            "exchangeSegment": segment,
            "transactionType": side_val,
            "orderType": ot_val,
            "productType": pt_val,
            "validity": v_val,
            "quantity": quantity,
        }
        if price and price > 0:
            from domain.utils.price import to_wire_float

            payload["price"] = to_wire_float(price)
        if trigger_price and trigger_price > 0:
            from domain.utils.price import to_wire_float

            payload["triggerPrice"] = to_wire_float(trigger_price)
        if correlation_id:
            payload["correlationId"] = correlation_id
        return payload

    @staticmethod
    def _build_placed_order(
        data: dict,
        symbol: str,
        exchange: Any,
        side_val: str,
        ot_val: str,
        pt_val: str,
        v_val: str,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        correlation_id: str,
    ) -> Order:
        """Build an Order domain object from a place-order API response."""
        order_id = str(data.get("data", {}).get("orderId") or data.get("orderId") or "")
        return Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
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

    # ── Event publishing ────────────────────────────────────────────────

    def _publish(self, event_type: str, order: Order) -> None:
        if self._event_bus is None:
            return
        from domain.ports.execution_context import is_oms_managed_submit

        if is_oms_managed_submit():
            return
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                {"order": order},
                symbol=order.symbol,
                source="DhanOrdersAdapter",
            )
        )
