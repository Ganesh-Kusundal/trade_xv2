"""BaseWireAdapter helpers — decimal, datetime, enum_value."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

import pytest

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, ProductType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Price, Quantity
from plugins.brokers.common.wire import BaseWireAdapter
from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.upstox.wire import UpstoxWire


class _Color(Enum):
    RED = "red"


def test_to_decimal_from_str_int_float() -> None:
    assert BaseWireAdapter.to_decimal("12.50") == Decimal("12.50")
    assert BaseWireAdapter.to_decimal(7) == Decimal("7")
    assert BaseWireAdapter.to_decimal(Decimal("1.5")) == Decimal("1.5")


def test_to_datetime_from_iso_and_datetime() -> None:
    raw = "2024-01-15T10:30:00+00:00"
    dt = BaseWireAdapter.to_datetime(raw)
    assert isinstance(dt, datetime)
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.tzinfo is not None

    already = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
    assert BaseWireAdapter.to_datetime(already) is already


def test_enum_value() -> None:
    assert BaseWireAdapter.enum_value(OrderSide.BUY) == "BUY"
    assert BaseWireAdapter.enum_value(_Color.RED) == "red"
    assert BaseWireAdapter.enum_value("plain") == "plain"


def test_dhan_security_id_before_load() -> None:
    wire = DhanWire()
    with pytest.raises(KeyError, match="no Dhan securityId"):
        wire.security_id(InstrumentId.parse("NSE:RELIANCE"))


def test_dhan_register_and_lookup() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    assert wire.security_id(InstrumentId.parse("NSE:RELIANCE")) == "2885"


def test_upstox_instrument_key_before_load() -> None:
    wire = UpstoxWire()
    with pytest.raises(KeyError, match="no Upstox instrument_key"):
        wire.instrument_key(InstrumentId.parse("MCX:GOLD"))


def test_upstox_instrument_key_unmapped_raises() -> None:
    """An unmapped canonical id must never pass through as a fake instrument_key."""
    wire = UpstoxWire()
    with pytest.raises(KeyError, match="no Upstox instrument_key"):
        wire.instrument_key(InstrumentId.parse("NSE:RELIANCE"))


def test_upstox_register_and_lookup() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    assert wire.instrument_key(InstrumentId.parse("NSE:RELIANCE")) == "NSE_EQ:RELIANCE"


# ---------------------------------------------------------------------------
# Product type tests
# ---------------------------------------------------------------------------

def _make_command(product_type: ProductType | None = None) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=__import__("uuid").uuid4()),
        product_type=product_type,
    )


def test_dhan_product_type_default() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    body = wire.from_place_command(_make_command())
    assert body["productType"] == "INTRADAY"


def test_dhan_product_type_custom() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    body = wire.from_place_command(_make_command(product_type=ProductType.DELIVERY))
    assert body["productType"] == "CNC"


def test_upstox_product_type_default() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    body = wire.from_place_command(_make_command())
    assert body["product"] == "I"


def test_upstox_product_type_custom() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    body = wire.from_place_command(_make_command(product_type=ProductType.DELIVERY))
    assert body["product"] == "D"


def test_upstox_product_type_margin_unsupported_raises() -> None:
    """Upstox has no MARGIN product distinct from MTF — must raise, not guess."""
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    with pytest.raises(ValueError, match="does not support product_type"):
        wire.from_place_command(_make_command(product_type=ProductType.MARGIN))


# ---------------------------------------------------------------------------
# Segment tests
# ---------------------------------------------------------------------------

def test_dhan_segment_nse() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("NSE:RELIANCE")) == "NSE_EQ"


def test_dhan_segment_nfo() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("NFO:NIFTY")) == "NSE_FNO"


def test_dhan_segment_mcx() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("MCX:GOLD")) == "MCX_COMM"


def test_dhan_segment_bse() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("BSE:RELIANCE")) == "BSE_EQ"


def test_unknown_exchange_rejected_at_construction() -> None:
    """Invalid exchanges are now caught at InstrumentId construction, not at
    wire.get_segment() time — the old "unknown exchange -> default NSE_EQ"
    fallback in get_segment() is unreachable since no valid InstrumentId can
    carry an unrecognized exchange code."""
    with pytest.raises(ValueError, match="Invalid exchange"):
        InstrumentId.parse("XYZ:FOO")


def test_upstox_segment_nse() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("NSE:RELIANCE")) == "NSE_EQ"


def test_upstox_segment_nfo() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("NFO:NIFTY")) == "NSE_FO"


def test_upstox_segment_mcx() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("MCX:GOLD")) == "MCX_FO"


def test_upstox_segment_bse() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("BSE:RELIANCE")) == "BSE_EQ"


def test_dhan_segment_bfo() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("BFO:SENSEX")) == "BSE_FNO"


def test_dhan_segment_cds() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("CDS:USDINR")) == "NSE_CURRENCY"


def test_dhan_segment_idx() -> None:
    assert DhanWire().get_segment(InstrumentId.parse("IDX:NIFTY")) == "IDX_I"


def test_upstox_segment_bfo() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("BFO:SENSEX")) == "BSE_FO"


def test_upstox_segment_cds() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("CDS:USDINR")) == "NCD_FO"


def test_upstox_segment_idx() -> None:
    assert UpstoxWire().get_segment(InstrumentId.parse("IDX:NIFTY50")) == "NSE_INDEX"


# ---------------------------------------------------------------------------
# Trigger price tests
# ---------------------------------------------------------------------------

def _make_command_with_trigger(trigger=None, product_type=None):
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.STOP,
        quantity=Quantity(value=Decimal("1")),
        price=Price(value=Decimal("100.0")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=__import__("uuid").uuid4()),
        product_type=product_type,
        trigger_price=trigger,
    )


def test_dhan_trigger_price_included() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    cmd = _make_command_with_trigger(trigger=Price(value=Decimal("95.0")))
    body = wire.from_place_command(cmd)
    assert body["triggerPrice"] == 95.0


def test_dhan_trigger_price_absent() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    cmd = _make_command_with_trigger()
    body = wire.from_place_command(cmd)
    assert "triggerPrice" not in body


def test_upstox_trigger_price_included() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    cmd = _make_command_with_trigger(trigger=Price(value=Decimal("95.0")))
    body = wire.from_place_command(cmd)
    assert body["trigger_price"] == 95.0


def test_upstox_trigger_price_absent() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    cmd = _make_command_with_trigger()
    body = wire.from_place_command(cmd)
    assert "trigger_price" not in body


# ---------------------------------------------------------------------------
# Round-trip canonical InstrumentId tests
# ---------------------------------------------------------------------------

def test_dhan_to_order_canonical_instrument_id() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    order = wire.to_order({"orderId": "123", "securityId": "2885", "orderStatus": "TRADED",
                           "transactionType": "BUY", "orderType": "LIMIT", "quantity": "10",
                           "price": "100", "filledQty": "10"})
    assert order.instrument_id.value == "NSE:RELIANCE"


def test_dhan_to_position_canonical_instrument_id() -> None:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    pos = wire.to_position({"securityId": "2885", "netQty": "10", "avgCostPrice": "100",
                            "realizedProfit": "0", "unrealizedProfit": "50"})
    assert pos.instrument_id.value == "NSE:RELIANCE"


def test_upstox_to_order_canonical_instrument_id() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    order = wire.to_order({"order_id": "123", "instrument_token": "NSE_EQ:RELIANCE",
                           "status": "complete", "transaction_type": "BUY",
                           "order_type": "LIMIT", "quantity": "10", "price": "100",
                           "filled_quantity": "10"})
    assert order.instrument_id.value == "NSE:RELIANCE"


def test_upstox_to_position_canonical_instrument_id() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ:RELIANCE")
    pos = wire.to_position({"instrument_token": "NSE_EQ:RELIANCE", "quantity": "10",
                            "average_price": "100", "realised": "0", "unrealised": "50"})
    assert pos.instrument_id.value == "NSE:RELIANCE"


# ---------------------------------------------------------------------------
# Unresolved instrument IDs must raise, never fabricate a fake symbol
# ---------------------------------------------------------------------------

def test_dhan_to_position_unmapped_id_raises() -> None:
    from shared.errors import MappingError

    wire = DhanWire()
    with pytest.raises(MappingError):
        wire.to_position({"securityId": "1181", "netQty": "10", "avgCostPrice": "100",
                          "realizedProfit": "0", "unrealizedProfit": "0"})


def test_dhan_to_order_unmapped_id_raises() -> None:
    from shared.errors import MappingError

    wire = DhanWire()
    with pytest.raises(MappingError):
        wire.to_order({"orderId": "123", "securityId": "999999", "orderStatus": "TRADED",
                       "transactionType": "BUY", "orderType": "LIMIT", "quantity": "10"})


def test_upstox_to_position_unmapped_id_raises() -> None:
    from shared.errors import MappingError

    wire = UpstoxWire()
    with pytest.raises(MappingError):
        wire.to_position({"instrument_token": "NSE_EQ|UNKNOWN", "quantity": "10",
                          "average_price": "100", "realised": "0", "unrealised": "0"})


def test_upstox_to_order_unmapped_id_raises() -> None:
    from shared.errors import MappingError

    wire = UpstoxWire()
    with pytest.raises(MappingError):
        wire.to_order({"order_id": "123", "instrument_token": "NSE_EQ|UNKNOWN",
                       "status": "complete", "transaction_type": "BUY",
                       "order_type": "LIMIT", "quantity": "10"})
