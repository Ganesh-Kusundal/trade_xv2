"""Order adapter — order placement and cancellation operations.

Responsibility: Place and cancel orders via Upstox broker adapters.
Thread-safe: Delegates to thread-safe order command adapter.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.common.core.domain import (
    ExchangeSegment,
    OrderRequest,
    OrderResponse,
    OrderType,
    ProductType,
    Side,
    Validity,
)

from brokers.upstox.adapters.symbol_resolver import SymbolResolverAdapter

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker

logger = logging.getLogger(__name__)


class OrderAdapter:
    """Adapter for order placement and cancellation operations.
    
    Encapsulates:
    - Order placement with validation and risk checks
    - Order cancellation with error handling
    - Correlation ID tracking for order tracing
    - Live order security guard
    
    Thread Safety:
        Delegates to broker's order_command adapter which maintains its own
        thread safety. This adapter is stateless and thread-safe.
    
    Example::
    
        adapter = OrderAdapter(broker)
        response = adapter.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=1,
            price=Decimal("2500"),
            order_type="LIMIT",
        )
        cancel_response = adapter.cancel_order(order_id="12345")
    """
    
    def __init__(self, broker: UpstoxBroker) -> None:
        """Initialize with broker facade.
        
        Args:
            broker: UpstoxBroker instance providing access to order adapters
        """
        self._broker = broker
    
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
        transport_only: bool = False,
    ) -> OrderResponse:
        """Place an order via Upstox.
        
        Builds a canonical OrderRequest and delegates to the order-command
        adapter, which handles instrument resolution, risk checks,
        idempotency, and payload construction.
        
        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price (ignored for MARKET orders)
            order_type: "MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"
            product_type: "INTRADAY", "MARGIN", "CNC"
            validity: "DAY" or "IOC"
            trigger_price: Trigger price for stop-loss orders
            correlation_id: Optional correlation ID for tracing
            is_amo: Whether this is an After Market Order
            
        Returns:
            OrderResponse with success status and order ID
        """
        if correlation_id is None:
            try:
                from brokers.common.correlation import get_current_correlation_id
                correlation_id = get_current_correlation_id()
            except ImportError:
                pass
        
        # Security guard: prevent live orders if disabled
        if not self._broker.settings.allow_live_orders:
            return OrderResponse.fail(
                "Live orders are disabled. Set allow_live_orders=True in configuration."
            )
        
        # Validate the exchange string early
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        UpstoxDomainMapper.segment_to_wire(exchange)
        
        exchange_segment = SymbolResolverAdapter.resolve_exchange_segment(
            exchange, symbol
        )
        request = OrderRequest(
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
            is_amo=is_amo,
            transport_only=transport_only,
        )
        
        try:
            response = self._broker.order_command.place_order(request)
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
    
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via Upstox.
        
        Args:
            order_id: Upstox order ID to cancel
            
        Returns:
            OrderResponse with success reflecting the broker's response.
            Network/auth errors are reported as success=False with a
            diagnostic error code; this method never raises.
        """
        if not self._broker.settings.allow_live_orders:
            return OrderResponse.fail(
                message=(
                    "Live order cancellation is disabled. "
                    "Set allow_live_orders=True in configuration."
                ),
                error_code="BRO_ERR_NOT_SUPPORTED",
            )
        
        try:
            body = self._broker.order_client.cancel_order(order_id)
        except Exception as exc:
            logger.warning(
                "upstox_cancel_network_error",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return OrderResponse.fail(
                message=f"network error: {exc}",
                error_code="BRO_ERR_CONNECTION_FAILED",
            )
        
        if not isinstance(body, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(body)},
            )
        
        broker_status = str(body.get("status", "")).lower()
        if broker_status in {"success", "ok"}:
            return OrderResponse.ok(
                order_id=order_id,
                message=str(body.get("message", "Order cancelled")),
                raw_payload=body,
            )
        
        return OrderResponse.fail(
            message=str(
                body.get("errors", [{}])[0].get("message")
                if isinstance(body.get("errors"), list) and body.get("errors")
                else body.get("message", "Cancel failed")
            ),
            error_code=str(
                body.get("errors", [{}])[0].get("errorCode")
                if isinstance(body.get("errors"), list) and body.get("errors")
                else ""
            ),
            raw_payload=body,
        )
