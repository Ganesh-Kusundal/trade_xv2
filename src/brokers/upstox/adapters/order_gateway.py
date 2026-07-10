"""OrderGateway — place, cancel, modify, and query orders.

Responsibility: Order lifecycle management including safety guards,
post-cancellation verification, exchange segment resolution, and order/trade book queries.
Thread-safe: Delegates to order_command and portfolio adapters.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from domain import (
    ExchangeSegment,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Trade,
    Validity,
)

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

        gw = OrderGateway(broker, order_command, portfolio_adapter)
        response = gw.place_order("RELIANCE", "NSE", "BUY", 1)
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

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
        is_amo: bool = False,
    ) -> OrderResponse:
        """Place an order via Upstox.

        Builds a canonical :class:`OrderRequest` and delegates to the
        order-command adapter, which handles instrument resolution,
        risk checks, idempotency, and payload construction.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`infrastructure.correlation.with_correlation`)
        is used for tracing.

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

        if correlation_id is None:
            try:
                from domain.correlation import get_current_correlation_id

                correlation_id = get_current_correlation_id()
            except ImportError:
                pass

        from brokers.upstox.mappers.domain_mapper import PROVIDER_IS_AMO

        exchange_segment = self._resolve_exchange_segment(exchange, symbol)
        from domain.models.dtos import BrokerOrderPayload

        request = BrokerOrderPayload(
            symbol=symbol,
            exchange=exchange,
            exchange_segment=exchange_segment,
            transaction_type=Side(side.upper()),
            quantity=quantity,
            price=price,
            trigger_price=trigger_price if trigger_price > Decimal("0") else None,
            order_type=OrderType(order_type.upper()),
            product_type=ProductType(product_type.upper()),
            validity=Validity(validity.upper()),
            correlation_id=correlation_id,
            provider_metadata={PROVIDER_IS_AMO: is_amo},
        )

        try:
            response = self._order_command.place_order(request)
        except Exception as e:
            logger.warning(
                "order_placement_failed",
                extra={
                    "correlation_id": correlation_id,
                    "symbol": symbol,
                    "side": side,
                    "error": str(e),
                },
            )
            return OrderResponse.fail(str(e))

        # Log failed responses from adapter (risk checks, validation, etc.)
        if not response.success:
            logger.warning(
                "order_placement_rejected",
                extra={
                    "correlation_id": correlation_id,
                    "symbol": symbol,
                    "side": side,
                    "error": response.message,
                },
            )
            return response

        if response.success and correlation_id:
            logger.info(
                "order_placed",
                extra={
                    "correlation_id": correlation_id,
                    "order_id": response.order_id,
                    "symbol": symbol,
                    "side": side,
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
        from domain import OrderResponse

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
            return OrderResponse.fail(str(exc))

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
