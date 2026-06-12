"""Order safety validator and preview result.

Design reference: Trade_J ``DhanOrderValidator``.

Validation is intentionally **advisory-first** (produces warnings rather than
blocking errors) for notional limits; all other rule violations are
hard errors that prevent placement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers.common.core.enums import ProductType
from brokers.common.core.models import OrderPreview, OrderRequest
from brokers.dhan.instrument_service import InstrumentService


class DhanOrderValidator:
    """Safety validator matching Trade_J's DhanOrderValidator."""

    HIGH_NOTIONAL_WARNING = Decimal("50000")

    def __init__(
        self,
        instrument_service: InstrumentService,
        settings: Any = None,
        *,
        strict: bool = False,
    ) -> None:
        self._instrument_service = instrument_service
        self._settings = settings
        self._strict = strict

    def validate(self, request: OrderRequest) -> OrderPreview:
        """Validate an order before submission.

        :param request: The :class:`~broker.core.models.OrderRequest` to check.
        :returns: An :class:`OrderPreview` with ``valid`` flag, errors, warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        result = self._instrument_service.resolve_symbol(
            symbol=request.symbol,
            exchange=request.exchange,
        )
        definition = result.definition if result.is_single else None
        if definition is None:
            errors.append("Instrument not found in catalog")
            return OrderPreview(valid=False, errors=errors, warnings=warnings)

        # Product × segment compatibility
        if request.product_type not in ProductType.valid_for(request.exchange_segment.value):
            errors.append(
                f"Product {request.product_type.value} is not valid for "
                f"{request.exchange_segment.value}"
            )

        # Lot-size multiple
        if definition.lot_size and request.quantity % definition.lot_size != 0:
            errors.append(f"Quantity must be a multiple of lot size {definition.lot_size}")

        # Notional warning / error
        notional = request.estimated_value()
        if notional and notional > self.HIGH_NOTIONAL_WARNING:
            message = f"Order notional {notional} exceeds Rs. {self.HIGH_NOTIONAL_WARNING}"
            if self._strict:
                errors.append(message)
            else:
                warnings.append(message)

        return OrderPreview(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            notional=notional,
        )
