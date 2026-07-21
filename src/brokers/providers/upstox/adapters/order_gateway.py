"""OrderGateway — place, cancel, modify, and query orders.

Responsibility: Order lifecycle management including safety guards,
post-cancellation verification, exchange segment resolution, and order/trade book queries.
Thread-safe: Delegates to order_command and portfolio adapters.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from domain.market_enums import ExchangeSegment
from domain.entities import Order, OrderResponse, Trade
from domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from domain.constants import DEFAULT_EXCHANGE
from domain.orders.requests import OrderRequest

logger = logging.getLogger(__name__)


class OrderGateway:
    """Order operations — place, cancel, modify, orderbook, trade book.

    Encapsulates:
    - Order placement with safety guards and instrument resolution
    - Order cancellation with post-cancellation verification
    - Order modification
    - Single order lookup with orderbook fallback
    - Order book and trade book queries

    Thread Safety:
        All methods are thread-safe. Delegates to broker adapters.

    Example::

        from domain.orders.requests import OrderRequest
        from domain.enums import Side

        gw = OrderGateway(broker, order_command, portfolio_adapter)
        response = gw.place_order(OrderRequest(symbol="RELIANCE", exchange="NSE", transaction_type=Side.BUY, quantity=1))
        book = gw.get_orderbook()
    """

    def __init__(self, broker: Any, order_command: Any, portfolio_adapter: Any) -> None:
        """Initialize with broker facade, order command adapter, and portfolio adapter.

        Args:
            broker: UpstoxBroker instance (for settings access)
            order_command: Order command adapter
            portfolio_adapter: PortfolioAdapter (for orderbook/trade queries)
        """
        self._broker = broker
        self._order_command = order_command
        self._portfolio = portfolio_adapter

    # ── Order placement ─────────────────────────────────────────────────

    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order via Upstox.

        Accepts a typed :class:`OrderRequest` and delegates to the
        order-command adapter, which handles instrument resolution,
        risk checks, idempotency, and payload construction.

        The OMS owns all pre-submit risk validation; the broker adapter
        enforces its own boundary checks independently.
        """
        # Security guard: prevent live orders if disabled or analytics-only
        if self._broker.settings.analytics_only:
            return OrderResponse.fail("Analytics-only mode: live orders are blocked.")
        if not self._broker.settings.allow_live_orders:
            return OrderResponse.fail(
                "Live orders are disabled. Set allow_live_orders=True in configuration."
            )

        if not request.correlation_id:
            try:
                from domain.correlation import get_current_correlation_id

                object.__setattr__(request, "correlation_id", get_current_correlation_id())
            except ImportError:
                pass

        from brokers.providers.upstox.mappers.domain_mapper import PROVIDER_IS_AMO
        from domain.models.dtos import BrokerOrderPayload

        exchange_segment = self._resolve_exchange_segment(request.exchange, request.symbol)

        # Build BrokerOrderPayload from the OrderRequest, preserving transport metadata
        if isinstance(request, BrokerOrderPayload):
            payload = request
        else:
            is_amo = False
            payload = BrokerOrderPayload(
                symbol=request.symbol,
                exchange=request.exchange,
                exchange_segment=exchange_segment,
                transaction_type=request.transaction_type,
                quantity=request.quantity,
                price=request.price,
                trigger_price=request.trigger_price,
                order_type=request.order_type,
                product_type=request.product_type,
                validity=request.validity,
                correlation_id=request.correlation_id,
                disclosed_quantity=request.disclosed_quantity,
                provider_metadata={PROVIDER_IS_AMO: is_amo},
            )

        from brokers.common.util import enum_value

        try:
            response = self._order_command.place_order(payload)
        except Exception as e:
            from brokers.common.transport_errors import order_response_from_transport_error

            logger.warning(
                "order_placement_failed",
                extra={
                    "correlation_id": request.correlation_id,
                    "symbol": request.symbol,
                    "side": enum_value(request.transaction_type),
                    "error": str(e),
                },
            )
            return order_response_from_transport_error(e)

        # Log failed responses from adapter (risk checks, validation, etc.)
        if not response.success:
            logger.warning(
                "order_placement_rejected",
                extra={
                    "correlation_id": request.correlation_id,
                    "symbol": request.symbol,
                    "side": enum_value(request.transaction_type),
                    "error": response.message,
                },
            )
            return response

        if response.success and request.correlation_id:
            logger.info(
                "order_placed",
                extra={
                    "correlation_id": request.correlation_id,
                    "order_id": response.order_id,
                    "symbol": request.symbol,
                    "side": enum_value(request.transaction_type),
                },
            )

        return response

    # ── Order cancellation ──────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order with post-cancellation verification.

        H1 Critical Fix: After sending cancel request, verifies order actually
        reached cancelled state. Detects race condition where order was filled
        between cancel send and response.

        Returns:
            OrderResponse with success=True if cancelled, or
            OrderResponse.fail with error_code="ALREADY_EXECUTED" if order
            was already filled before cancel could complete.
        """
        # Safety guard: prevent live order cancellations if disabled
        if self._broker.settings.analytics_only:
            return OrderResponse.fail("Analytics-only mode: live orders are blocked.")
        if not self._broker.settings.allow_live_orders:
            return OrderResponse.fail(
                "Live orders are disabled. Set allow_live_orders=True in configuration."
            )

        # Step 1: Send cancel request
        response = self._order_command.cancel_order(order_id)

        # Step 2: Post-cancellation verification (H1 fix)
        if response.success:
            order = self.get_order(order_id)
            if order and order.status in (OrderStatus.FILLED,):
                return OrderResponse.fail(
                    message=f"Order {order_id} was already filled before cancel completed",
                    status=OrderStatus.FILLED,
                )

        return response

    # ── Single order lookup ─────────────────────────────────────────────

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID via direct lookup.

        Uses the UpstoxOrderQueryAdapter.get_order() method which calls
        the order details endpoint directly, avoiding a full orderbook
        fetch. This halves API calls in cancel_order() verification.

        H1 Critical Fix: Enables post-cancellation verification by allowing
        lookup of individual orders.

        Performance: O(1) single-order fetch instead of O(n) orderbook scan.

        Args:
            order_id: Broker order ID to look up

        Returns:
            Order if found, None if not in orderbook
        """
        order_query = getattr(self._broker, "order_query", None)
        if order_query is not None:
            return order_query.get_order(order_id)
        # Fallback: scan orderbook (backward compat with minimal test mocks)
        orderbook = self.get_orderbook()
        for order in orderbook:
            if order.order_id == order_id:
                return order
        return None

    # ── Order modification ─────────────────────────────────────────────

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an order via Upstox V3 API."""
        from domain.entities import OrderResponse

        # Safety guard: prevent live order modifications if disabled
        if self._broker.settings.analytics_only:
            return OrderResponse.fail("Analytics-only mode: live orders are blocked.")
        if not self._broker.settings.allow_live_orders:
            return OrderResponse.fail(
                "Live orders are disabled. Set allow_live_orders=True in configuration."
            )

        try:
            result = self._order_command.modify_order(order_id, **changes)
            # ENG-002: order_command.modify_order returns OrderResponse (adapter
            # contract). Legacy dict payloads still accepted for older mocks.
            if isinstance(result, OrderResponse):
                return result
            if isinstance(result, dict) and str(result.get("status", "")).lower() in {
                "success",
                "ok",
            }:
                return OrderResponse.ok(order_id=order_id, message="Order modified")
            message = (
                result.get("message", "modify failed")
                if isinstance(result, dict)
                else "modify failed"
            )
            return OrderResponse.fail(message)
        except Exception as exc:
            from brokers.common.transport_errors import order_response_from_transport_error

            return order_response_from_transport_error(exc)

    # ── Order / Trade book ─────────────────────────────────────────────

    def get_orderbook(self) -> list[Order]:
        """Fetch current order book.

        Returns:
            List of Order dataclasses
        """
        return self._portfolio.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        """Get today's trade book from the Upstox V2 trades-for-day endpoint.

        Returns:
            List of Trade dataclasses
        """
        return self._portfolio.get_trades()

    # ── Exchange segment resolution ─────────────────────────────────────

    def _resolve_exchange_segment(self, exchange: str, symbol: str = "") -> ExchangeSegment:
        """Map user-facing exchange string to canonical ExchangeSegment.

        For recognised index symbols (NIFTY, BANKNIFTY, etc.) the segment is
        set to IDX_I regardless of the exchange string.

        Args:
            exchange: User-facing exchange string (e.g., "NSE", "NFO")
            symbol: Optional symbol for index detection

        Returns:
            Canonical ExchangeSegment enum value
        """
        from config.indices import index_upstox_key
        from domain.exchange_segments import parse_segment

        # Index symbols use a dedicated segment
        if symbol and index_upstox_key(symbol) is not None:
            return ExchangeSegment.IDX_I

        parsed = parse_segment(exchange)
        if parsed is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")
        return parsed
