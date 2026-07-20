"""Margin adapter — calculate margin requirements for orders."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.common.api import MarginProvider, MarginResult
from brokers.common.oms.margin_provider import parse_margin_response
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.domain import MarginRequest, MarginResponse
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.resilience.invariants import assert_dhan_payload
from domain.value_objects.price import to_wire_float

logger = logging.getLogger(__name__)


class MarginAdapter(MarginProvider):
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def calculate(self, request: MarginRequest) -> MarginResponse:
        """Calculate margin required for an order."""
        errors = self._validate_request(request)
        if errors:
            msg = "; ".join(errors)
            logger.warning(
                "margin_validation_failed",
                extra={"symbol": request.symbol, "errors": errors},
            )
            raise ValueError(f"Margin request validation failed: {msg}")

        ref = self._identity.resolve_ref(request.symbol, request.exchange)
        segment = ref.exchange_segment

        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "transactionType": "BUY",
            "orderType": request.order_type,
            "productType": request.product_type,
            "quantity": request.quantity,
        }

        if request.price is not None and request.price > 0:
            payload["price"] = to_wire_float(request.price)

        if request.trigger_price is not None and request.trigger_price > 0:
            payload["triggerPrice"] = to_wire_float(request.trigger_price)

        assert_dhan_payload(payload, context="margin.calculate")

        data = self._client.post("/margincalculator", json=payload)
        response_data = data.get("data", data)
        parsed = parse_margin_response(response_data if isinstance(response_data, dict) else {})
        margin_response = MarginResponse(
            total_margin=parsed.required_margin,
            order_margin=Decimal(str(response_data.get("orderMargin", parsed.required_margin)))
            if isinstance(response_data, dict)
            else parsed.required_margin,
            exposure_margin=parsed.exposure_margin or Decimal("0"),
            available_margin=parsed.available_margin if parsed.available_margin else None,
            span_margin=parsed.span_margin,
        )

        logger.info(
            "margin_calculated",
            extra={
                "symbol": request.symbol,
                "quantity": request.quantity,
                "total_margin": str(margin_response.total_margin),
            },
        )
        return margin_response

    def calculate_margin(self, payload: dict) -> dict:
        """MarginProvider port — accept a standardised payload dict."""
        req = MarginRequest(
            symbol=str(payload["symbol"]),
            exchange=str(payload.get("exchange", "NSE")),
            quantity=int(payload["quantity"]),
            order_type=str(payload.get("order_type", "MARKET")),
            product_type=str(payload.get("product_type", "INTRADAY")),
            price=Decimal(str(payload["price"])) if payload.get("price") is not None else None,
        )
        result = self.calculate(req)
        return {
            "totalMargin": result.total_margin,
            "orderMargin": result.order_margin,
            "exposureMargin": result.exposure_margin,
            "availableMargin": result.available_margin,
            "spanMargin": result.span_margin,
        }

    def calculate_margin_for_order(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        product_type: str,
        order_type: str,
    ) -> MarginResult:
        raw = self.calculate_margin(
            {
                "symbol": symbol,
                "exchange": exchange,
                "quantity": quantity,
                "price": price,
                "product_type": product_type,
                "order_type": order_type,
            }
        )
        return parse_margin_response(raw)

    def _validate_request(self, request: MarginRequest) -> list[str]:
        errors = []
        if request.quantity <= 0:
            errors.append(f"Quantity must be positive, got {request.quantity}")
        if request.order_type in ("LIMIT", "STOP_LOSS") and (
            request.price is None or request.price <= 0
        ):
            errors.append("LIMIT/STOP_LOSS orders require price > 0")
        return errors
