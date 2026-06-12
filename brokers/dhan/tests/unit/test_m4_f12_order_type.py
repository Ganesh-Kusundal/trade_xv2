"""M4 — F12 regression: ``OrderType`` is imported in the order command adapter.

Pre-fix: ``DhanOrderCommandAdapter._payload_from_request`` referenced
``OrderType`` without importing it from ``brokers.common.core.enums``.
Every LIMIT order raised ``NameError: name 'OrderType' is not defined``.
Market orders worked by accident because the ``if`` branch was skipped.

Post-fix: the import is in place and the LIMIT branch executes cleanly.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.common.core.enums import (
    ExchangeSegment,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.models import OrderRequest
from brokers.dhan.orders.order_command_adapter import DhanOrderCommandAdapter

pytestmark = pytest.mark.unit


def _build_request(order_type: OrderType = OrderType.LIMIT) -> OrderRequest:
    """Build a minimal OrderRequest — just enough to exercise the LIMIT branch."""
    return OrderRequest(
        symbol="RELIANCE",
        security_id="2885",
        exchange="NSE",
        exchange_segment=ExchangeSegment.NSE,
        transaction_type=TransactionType.BUY,
        quantity=1,
        order_type=order_type,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        price=Decimal("2500.00"),
    )


def _build_adapter() -> DhanOrderCommandAdapter:
    """Build a DhanOrderCommandAdapter with stub dependencies."""
    order_client = MagicMock()
    instrument_service = MagicMock()
    instrument_service.resolve_to_wire.return_value = MagicMock(
        security_id="2885",
        wire_segment="NSE_EQ",
    )
    validator = MagicMock()
    validator.validate.return_value = MagicMock(valid=True, errors=())
    return DhanOrderCommandAdapter(
        order_client=order_client,
        instrument_service=instrument_service,
        validator=validator,
    )


class TestF12OrderTypeImport:
    """F12 — OrderType must be importable and usable in the adapter."""

    def test_limit_order_builds_payload_without_name_error(self) -> None:
        adapter = _build_adapter()
        req = _build_request(order_type=OrderType.LIMIT)
        # The bug: this raised NameError: name 'OrderType' is not defined
        # because the module never imported it.
        payload = adapter._payload_from_request(req)
        assert payload["orderType"] == "LIMIT"
        assert payload["price"] == "2500.00"

    def test_market_order_builds_payload_without_name_error(self) -> None:
        adapter = _build_adapter()
        req = _build_request(order_type=OrderType.MARKET)
        payload = adapter._payload_from_request(req)
        assert payload["orderType"] == "MARKET"
