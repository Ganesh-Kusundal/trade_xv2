"""Order validation rules for the Dhan broker adapter.

Extracted from :class:`brokers.dhan.orders.OrdersAdapter` god class.
Owns pre-trade validation (lot size, product type, quantity, price, tick alignment).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from domain import OrderType, ProductType
from brokers.dhan.exceptions import DhanError
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT, DEFAULT_SEGMENT

logger = logging.getLogger(__name__)

# Segments where only INTRADAY and MARGIN product types are allowed
_DERIVATIVE_SEGMENTS = frozenset(
    {
        "NSE_FNO",
        "BSE_FNO",
        "MCX_COMM",
        "NSE_CURRENCY",
        "BSE_CURRENCY",
    }
)

# Product types NOT allowed for derivatives
_EQUITY_ONLY_PRODUCTS = frozenset({"CNC", "MTF"})


def _opt_dec(val) -> Decimal | None:
    """Convert a value to Decimal or return None."""
    if val in (None, ""):
        return None
    return Decimal(str(val))


class OrderValidator:
    """Validates order parameters before submission.

    Uses the instrument resolver to look up lot size, tick size, and
    segment for symbol/exchange pairs.
    """

    def __init__(self, resolver: object) -> None:
        self._resolver = resolver

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
        pt_val = (
            product_type.value
            if isinstance(product_type, ProductType)
            else str(product_type).upper()
        )

        if ot_val in ("LIMIT", "STOP_LOSS") and (price is None or price <= 0):
            errors.append(f"LIMIT/SL orders require price > 0, got {price}")

        # Resolve instrument for lot size and segment checks
        try:
            inst = self._resolver.resolve(symbol, exchange)
        except (DhanError, ValueError, KeyError) as exc:
            logger.warning(
                "instrument_resolve_failed",
                extra={"symbol": symbol, "exchange": exchange, "error": str(exc)},
            )
            errors.append(f"Instrument not found: {symbol} on {exchange}")
            return errors

        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)

        # Lot size check for derivatives
        if segment in _DERIVATIVE_SEGMENTS and inst.lot_size > 1 and quantity % inst.lot_size != 0:
            errors.append(
                f"Quantity {quantity} is not a multiple of lot size {inst.lot_size} "
                f"for {symbol} on {inst.exchange.value}"
            )

        # Tick size alignment check for priced orders
        if price is not None and price > 0:
            tick = getattr(inst, "tick_size", None)
            if tick is not None and tick > 0:
                from domain.utils.price import is_tick_aligned

                if not is_tick_aligned(price, tick):
                    errors.append(
                        f"Price {price} is not aligned to tick size {tick} "
                        f"for {symbol}"
                    )

        # Product type x segment check
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
