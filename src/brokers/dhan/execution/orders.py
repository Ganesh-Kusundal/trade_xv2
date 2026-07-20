"""Orders adapter — thin orchestrator (place, modify, cancel, orderbook, tradebook).

Delegates to focused collaborators:

* :class:`OrderValidator` — pre-trade validation rules
* :class:`OrderPlacer` — placement, slicing, idempotency
* :class:`OrderCanceller` — cancellation, modification, kill-switch

The ``_parse_order`` / ``_parse_trade`` helpers and all read-only query
methods remain here since they are simple data transformations without
side effects.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal

from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.execution.order_cancellation import OrderCanceller
from brokers.dhan.execution.order_placement import IdempotencyCache, OrderPlacer
from brokers.dhan.execution.order_validator import OrderValidator
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.segments import DEFAULT_SEGMENT, segment_to_exchange
from domain import (
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    ProductType,
    Trade,
)
from domain import Side as OrderSide
from brokers.dhan.execution.field_mapping import DHAN_FIELD_MAPPING
from domain.models.dtos import BrokerOrderPayload
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus.event_bus import EventBus

logger = logging.getLogger(__name__)


def _parse_timestamp(val: object) -> datetime | None:
    """Parse a timestamp from Dhan API response to datetime.

    Dhan returns ISO-8601 strings like '2026-06-30T10:15:30+05:30'.
    Returns None if the value is missing or unparseable.
    """
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


class OrdersAdapter:
    """Thin orchestrator composing validation, placement, and cancellation.

    Most public methods delegate to the focused collaborator that owns
    the operation.  Read-only queries (get_order, get_orderbook, etc.)
    are implemented directly.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        identity: DhanIdentityProvider | object,
        idempotency_cache: IdempotencyCache | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
        allow_live_orders: bool = False,
        allow_duck_identity: bool = False,
    ):
        self._client = client
        # Accept either a DhanIdentityProvider (production path) or a raw
        # SymbolResolver (legacy test fixtures). ``coerce_identity_provider``
        # guarantees the adapter holds a provider-shaped object so the
        # Dhan-internal contract is enforced end-to-end.
        self._identity = coerce_identity_provider(identity, allow_duck=allow_duck_identity)
        # Backward-compat shim for tests/code that still asks the adapter
        # for its underlying resolver. The resolver is owned by the
        # DhanIdentityProvider; this property delegates to it.
        self._resolver = self._identity.resolver
        self._idempotency = idempotency_cache or IdempotencyCache()
        self._event_bus = event_bus
        self._allow_live_orders = allow_live_orders

        # Focused collaborators
        self._validator = OrderValidator(self._resolver)
        self._placer = OrderPlacer(
            client=self._client,
            identity=self._identity,
            idempotency=self._idempotency,
            validator=self._validator,
            risk_manager=risk_manager,
            event_bus=event_bus,
            allow_live_orders=allow_live_orders,
        )
        self._canceller = OrderCanceller(
            client=self._client,
            event_bus=event_bus,
            allow_live_orders=allow_live_orders,
            get_order_fn=self.get_order,
        )

    # ── Validation (delegated) ──────────────────────────────────────────

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
        return self._validator.validate_order(
            symbol, exchange, quantity, order_type, product_type, price
        )

    def validate_order_warnings(
        self,
        quantity: int,
        price: Decimal | None = None,
    ) -> list[str]:
        """Return non-blocking warnings. High notional is the main check."""
        return self._validator.validate_order_warnings(quantity, price)

    # ── Order lifecycle (delegated) ─────────────────────────────────────

    def place_order(self, request: BrokerOrderPayload) -> OrderResponse:
        return self._placer.place_order(request)

    def place_slice_order(self, symbol: str, exchange: str, **kwargs) -> OrderResponse:
        return self._placer.place_slice_order(symbol, exchange, **kwargs)

    # ── Cancellation / modification (delegated) ─────────────────────────

    def modify_order(self, order_id: str, **changes: object) -> OrderResponse:
        return self._canceller.modify_order(order_id, **changes)

    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._canceller.cancel_order(order_id)

    def cancel_all_orders(self) -> list[tuple[str, bool]]:
        return self._canceller.cancel_all_orders()

    def kill_switch(self, enable: bool) -> bool:
        return self._canceller.kill_switch(enable)

    def status_kill_switch(self) -> dict:
        return self._canceller.status_kill_switch()

    # ── Read-only queries ──────────────────────────────────────────────

    def get_order(self, order_id: str) -> Order:
        data = self._client.get(f"/orders/{order_id}")
        raw = data.get("data", data) if isinstance(data, dict) else data
        return self._parse_order(raw if isinstance(raw, dict) else {})

    def get_order_by_correlation_id(self, correlation_id: str) -> Order:
        data = self._client.get(f"/orders/external/{correlation_id}")
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
        trades = [self._parse_trade(item) for item in (items if isinstance(items, list) else [])]
        logger.info("tradebook_fetched", extra={"count": len(trades)})
        return trades

    def get_order_status(self, order_id: str) -> OrderStatus:
        order = self.get_order(order_id)
        return order.status

    def get_trade_history(self, from_date: str, to_date: str, page: int = 0) -> list[Trade]:
        """Get trade history for a date range.

        Args:
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            page: Page number for pagination (default 0)

        Returns:
            List of Trade objects

        Raises:
            ValueError: If date format is invalid
        """
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_pattern.match(from_date):
            raise ValueError(f"Invalid from_date format: {from_date}. Expected YYYY-MM-DD")
        if not date_pattern.match(to_date):
            raise ValueError(f"Invalid to_date format: {to_date}. Expected YYYY-MM-DD")

        data = self._client.get(f"/trades/{from_date}/{to_date}/{page}")
        items = data.get("data", []) if isinstance(data, dict) else []
        trades = [self._parse_trade(item) for item in (items if isinstance(items, list) else [])]

        logger.info(
            "trade_history_fetched",
            extra={
                "from_date": from_date,
                "to_date": to_date,
                "page": page,
                "count": len(trades),
            },
        )
        return trades

    # ── Parsing helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_order(raw: dict) -> Order:
        return Order.from_broker_dict(
            raw, field_mapping=DHAN_FIELD_MAPPING, exchange_resolver=segment_to_exchange
        )

    @staticmethod
    def _parse_trade(raw: dict) -> Trade:
        """Parse trade from API response."""
        return Trade(
            trade_id=str(raw.get("tradeId", raw.get("id", ""))),
            order_id=str(raw.get("orderId", "")),
            symbol=raw.get("tradingSymbol", raw.get("symbol", "")),
            exchange=segment_to_exchange(raw.get("exchangeSegment", DEFAULT_SEGMENT)),
            side=OrderSide(raw.get("transactionType", "BUY")),
            quantity=raw.get("tradedQty", raw.get("quantity", 0)),
            price=Decimal(str(raw.get("tradedPrice", raw.get("price", 0)))),
            timestamp=_parse_timestamp(raw.get("tradedTime", raw.get("createdAt"))),
        )
