"""Margin adapter — calculate margin requirements for orders."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.domain import MarginRequest, MarginResponse
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)


class MarginAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver

    def calculate(self, request: MarginRequest) -> MarginResponse:
        """Calculate margin required for an order.

        Args:
            request: MarginRequest with order details

        Returns:
            MarginResponse with calculated margins

        Raises:
            ValueError: If request validation fails
        """
        # Validate request
        errors = self._validate_request(request)
        if errors:
            msg = "; ".join(errors)
            logger.warning("margin_validation_failed", extra={
                "symbol": request.symbol,
                "errors": errors,
            })
            raise ValueError(f"Margin request validation failed: {msg}")

        # Resolve instrument
        inst = self._resolver.resolve(request.symbol, request.exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")

        # Build API payload
        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": inst.security_id,
            "transactionType": "BUY",  # Default, API calculates both sides
            "orderType": request.order_type,
            "productType": request.product_type,
            "quantity": request.quantity,
        }

        if request.price is not None and request.price > 0:
            payload["price"] = float(request.price)

        if request.trigger_price is not None and request.trigger_price > 0:
            payload["triggerPrice"] = float(request.trigger_price)

        # Call API
        data = self._client.post("/margincalculator", json=payload)

        # Parse response
        response_data = data.get("data", data)
        margin_response = MarginResponse(
            total_margin=Decimal(str(response_data.get("totalMargin", 0))),
            order_margin=Decimal(str(response_data.get("orderMargin", 0))),
            exposure_margin=Decimal(str(response_data.get("exposureMargin", 0))),
            available_margin=Decimal(str(response_data["availableMargin"])) if "availableMargin" in response_data else None,
            span_margin=Decimal(str(response_data["spanMargin"])) if "spanMargin" in response_data else None,
        )

        logger.info("margin_calculated", extra={
            "symbol": request.symbol,
            "quantity": request.quantity,
            "total_margin": str(margin_response.total_margin),
        })

        return margin_response

    def _validate_request(self, request: MarginRequest) -> list[str]:
        """Validate margin request. Returns list of errors (empty = valid)."""
        errors = []

        if request.quantity <= 0:
            errors.append(f"Quantity must be positive, got {request.quantity}")

        if request.order_type in ("LIMIT", "STOP_LOSS") and (request.price is None or request.price <= 0):
            errors.append("LIMIT/STOP_LOSS orders require price > 0")

        return errors
