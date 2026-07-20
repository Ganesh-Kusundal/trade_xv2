"""Shared base for Upstox domain mapper — enums, constants, and pure helpers.

Extracted from ``domain_mapper.py`` so that the three specialised mapper
modules (equity, derivatives, options) can import shared converters
without creating circular imports.
"""

from __future__ import annotations

import logging

from domain import (
    ExchangeSegment,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from domain.parsing import parse_decimal, parse_int, parse_optional_str, parse_timestamp
from domain.status_mapper import StatusMapperRegistry

logger = logging.getLogger(__name__)

# ── Provider metadata key constants ──────────────────────────────────────
PROVIDER_IS_AMO: str = "is_amo"
PROVIDER_MARKET_PROTECTION: str = "market_protection"
PROVIDER_ALGO_NAME: str = "algo_name"

# ── Parsing helpers (delegated to shared utilities) ─────────────────────
str_or_none = parse_optional_str
to_decimal = parse_decimal
to_int = parse_int
parse_iso = parse_timestamp

# ── Wire-format constants ───────────────────────────────────────────────

_PRODUCT_TO_WIRE = {
    ProductType.INTRADAY: "I",
    ProductType.CNC: "D",
    ProductType.MARGIN: "M",
    ProductType.MTF: "MTF",
}
_WIRE_TO_PRODUCT = {v: k for k, v in _PRODUCT_TO_WIRE.items() if v not in ("D",)}

_VALIDITY_TO_WIRE = {
    Validity.DAY: "DAY",
    Validity.IOC: "IOC",
}
_WIRE_TO_VALIDITY = {v: k for k, v in _VALIDITY_TO_WIRE.items()}

_ORDER_TYPE_TO_WIRE = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP_LOSS: "SL",
    OrderType.STOP_LOSS_MARKET: "SL-M",
}
_WIRE_TO_ORDER_TYPE = {v: k for k, v in _ORDER_TYPE_TO_WIRE.items()}

_TXN_TO_WIRE = {
    Side.BUY: "BUY",
    Side.SELL: "SELL",
}
_WIRE_TO_TXN = {v: k for k, v in _TXN_TO_WIRE.items()}


# ── Status mapping ──────────────────────────────────────────────────────


def wire_status_to_domain_status(raw: str) -> OrderStatus:
    """Convert Upstox wire status string to canonical domain OrderStatus."""
    if not raw:
        return OrderStatus.OPEN
    return StatusMapperRegistry.normalize_strict(raw)


# ── Enum converters ─────────────────────────────────────────────────────


def product_to_wire(product: ProductType) -> str:
    return _PRODUCT_TO_WIRE.get(product, "I")


def product_from_wire(raw: str) -> ProductType:
    raw = (raw or "").upper()
    if raw in ("D", "DELIVERY"):
        return ProductType.CNC
    if raw in ("I", "INTRADAY", "MIS"):
        return ProductType.INTRADAY
    if raw in ("M", "MARGIN"):
        return ProductType.MARGIN
    if raw in ("MTF",):
        return ProductType.MTF
    return ProductType.INTRADAY


def validity_to_wire(validity: Validity) -> str:
    return _VALIDITY_TO_WIRE.get(validity, "DAY")


def validity_from_wire(raw: str) -> Validity:
    raw = (raw or "").upper()
    return _WIRE_TO_VALIDITY.get(raw, Validity.DAY)


def order_type_to_wire(order_type: OrderType) -> str:
    return _ORDER_TYPE_TO_WIRE.get(order_type, "MARKET")


def order_type_from_wire(raw: str) -> OrderType:
    raw = (raw or "").upper()
    if raw in ("MARKET", "MKT"):
        return OrderType.MARKET
    if raw in ("LIMIT", "LMT"):
        return OrderType.LIMIT
    if raw in ("SL", "STOP_LOSS", "STOPLOSS"):
        return OrderType.STOP_LOSS
    if raw in ("SL-M", "SLM", "STOP_LOSS_MARKET", "STOPLOSS_MARKET"):
        return OrderType.STOP_LOSS_MARKET
    return OrderType.MARKET


def txn_to_wire(txn: Side) -> str:
    return _TXN_TO_WIRE.get(txn, "BUY")


def txn_from_wire(raw: str) -> Side:
    raw = (raw or "").upper()
    return _WIRE_TO_TXN.get(raw, Side.BUY)


def segment_from_wire(segment: str) -> ExchangeSegment:
    from brokers.upstox.instruments.segment_mapper import UpstoxSegmentMapper

    return UpstoxSegmentMapper.to_safe(segment)


def segment_to_wire(segment: ExchangeSegment) -> str:
    from brokers.upstox.instruments.segment_mapper import _to_wire

    return _to_wire(segment)


def instrument_type_from_wire(raw: str) -> InstrumentType:
    raw = (raw or "").upper()
    if raw in ("EQ", "EQUITY", "STOCK"):
        return InstrumentType.EQUITY
    if raw in ("FUT", "FUTURE", "FUTURES"):
        return InstrumentType.FUTURES
    if raw in ("OPT", "OPTION", "OPTIONS"):
        return InstrumentType.OPTIONS
    if raw in ("IDX", "INDEX"):
        return InstrumentType.INDEX
    if raw in ("COM", "COMMODITY"):
        return InstrumentType.COMMODITY
    if raw in ("CUR", "CURRENCY"):
        return InstrumentType.CURRENCY
    return InstrumentType.EQUITY
