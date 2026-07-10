"""Portfolio adapter — positions, holdings, balance, convert position."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.resilience.invariants import assert_dhan_payload
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT, segment_to_exchange
from domain import Balance, Holding, Position, ProductType

logger = logging.getLogger(__name__)


class PortfolioAdapter:
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        # Read paths parse Dhan positions/holdings/balance responses.
        # Convert position is write-side and builds a security_id payload
        # via the identity provider.
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def get_positions(self) -> list[Position]:
        data = self._client.get("/positions")
        items = data.get("data", []) if isinstance(data, dict) else []
        positions = []
        for item in items if isinstance(items, list) else []:
            positions.append(
                Position(
                    symbol=str(item.get("tradingSymbol", "")),
                    exchange=segment_to_exchange(item.get("exchangeSegment", "NSE_EQ")),
                    quantity=int(item.get("netQuantity", 0)),
                    avg_price=Decimal(str(item.get("buyAveragePrice", 0))),
                    ltp=Decimal(str(item.get("lastPrice", 0))),
                    unrealized_pnl=Decimal(str(item.get("unrealizedPnl", 0))),
                    realized_pnl=Decimal(str(item.get("realizedPnl", 0))),
                    product_type=_parse_product(item.get("productType", "INTRADAY")),
                )
            )
        logger.info("positions_fetched", extra={"count": len(positions)})
        return positions

    def get_holdings(self) -> list[Holding]:
        data = self._client.get("/holdings")
        items = data.get("data", []) if isinstance(data, dict) else []
        holdings = []
        for item in items if isinstance(items, list) else []:
            qty = int(item.get("totalQty", item.get("quantity", 0)))
            avg_px = Decimal(str(item.get("avgCostPrice", item.get("costPrice", 0))))
            ltp = Decimal(str(item.get("lastTradedPrice", item.get("lastPrice", 0))))
            pnl_raw = item.get("pnlValue")
            if pnl_raw is not None:
                pnl = Decimal(str(pnl_raw))
            elif avg_px > 0 and ltp > 0:
                pnl = (ltp - avg_px) * qty
            else:
                pnl = Decimal("0")
            holdings.append(
                Holding(
                    symbol=str(item.get("tradingSymbol", "")),
                    exchange=segment_to_exchange(item.get("exchangeSegment", "NSE_EQ")),
                    quantity=qty,
                    available_quantity=int(
                        item.get("availableQty", item.get("availableQuantity", 0))
                    ),
                    avg_price=avg_px,
                    ltp=ltp,
                    pnl=pnl,
                )
            )
        logger.info("holdings_fetched", extra={"count": len(holdings)})
        return holdings

    def get_balance(self) -> Balance:
        data = self._client.get("/fundlimit")
        raw = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(raw, dict):
            logger.warning("balance_fetch_failed", extra={"reason": "unexpected_response_type"})
            return Balance()
        balance = Balance(
            available_balance=Decimal(
                str(raw.get("availabelBalance", raw.get("availableBalance", 0)))
            ),
            sod_limit=Decimal(str(raw.get("sodLimit", 0))),
            collateral_amount=Decimal(str(raw.get("collateralAmount", 0))),
            utilized_amount=Decimal(str(raw.get("utilizedAmount", 0))),
            withdrawable_balance=Decimal(str(raw.get("withdrawableBalance", 0))),
        )
        logger.info("balance_fetched", extra={"available_balance": str(balance.available_balance)})
        return balance

    def convert_position(
        self,
        symbol: str,
        *,
        exchange: str = "NSE",
        quantity: int,
        from_product_type: str,
        to_product_type: str,
        position_type: str = "LONG",
        security_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert open position product type (e.g. INTRADAY → CNC).

        Maps to ``POST /positions/convert``.

        Args:
            symbol: Trading symbol.
            exchange: Short exchange code (NSE / NFO / …).
            quantity: Shares/contracts to convert.
            from_product_type: Current product (INTRADAY, CNC, MARGIN, …).
            to_product_type: Desired product.
            position_type: LONG | SHORT.
            security_id: Optional override; resolved via identity when omitted.

        Returns:
            Raw API response dict (often empty body with 202 Accepted).
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        from_pt = str(from_product_type).upper()
        to_pt = str(to_product_type).upper()
        if from_pt == to_pt:
            raise ValueError("from_product_type and to_product_type must differ")

        if security_id:
            sec_id = str(security_id)
            segment = EXCHANGE_TO_SEGMENT.get(str(exchange).upper(), "NSE_EQ")
        else:
            ref = self._identity.resolve_ref(symbol, exchange)
            sec_id = ref.security_id_str()
            segment = ref.exchange_segment

        payload: dict[str, Any] = {
            "dhanClientId": self._client.client_id,
            "fromProductType": from_pt,
            "exchangeSegment": segment,
            "positionType": str(position_type).upper(),
            "securityId": sec_id,
            "tradingSymbol": symbol,
            "convertQty": int(quantity),
            "toProductType": to_pt,
        }
        assert_dhan_payload(payload, context="portfolio.convert_position")

        data = self._client.post("/positions/convert", json=payload)
        logger.info(
            "position_converted",
            extra={
                "symbol": symbol,
                "quantity": quantity,
                "from": from_pt,
                "to": to_pt,
            },
        )
        return data if isinstance(data, dict) else {"data": data}


def _parse_product(pt: str) -> ProductType:
    try:
        return ProductType(str(pt))
    except ValueError:
        return ProductType.INTRADAY
