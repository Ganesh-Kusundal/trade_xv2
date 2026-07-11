"""Canonical request/input shapes for broker operations.

These dataclasses represent the *input* side of broker operations —
order placement, modification, preview, and historical data queries.
They are distinct from the *output* models in ``models.py``.

Transport-only fields (``exchange_segment``, ``is_amo``, ``algo_name``,
``market_protection``, ``transport_only``) have been moved to
:class:`domain.models.dtos.BrokerOrderPayload`, which extends
``OrderRequest`` with broker-transport metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from domain.types import (
    OrderType,
    ProductType,
    Side,
    Validity,
)


@dataclass(slots=True, frozen=True)
class OrderRequest:
    """Input model for placing an order — domain fields only.

    Immutable by design. Broker-transport fields (exchange_segment, is_amo, etc.)
    have been moved to :class:`domain.models.dtos.BrokerOrderPayload`.
    Domain-level consumers (``OrderManager``, ``RiskManager``,
    ``OrderRepository``) should accept ``OrderRequest``; broker adapters that
    need transport metadata should accept ``BrokerOrderPayload``.

    Exchange default is a placeholder; composition roots should set exchange
    from :class:`market_data.market_surface.MarketSurface` (TOS-P5-030).
    """

    symbol: str = ""
    exchange: str = "NSE"
    transaction_type: Side = Side.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    correlation_id: str | None = None
    tag: str | None = None
    slice: bool = False
    # Portion of `quantity` visible in the order book (iceberg orders); the
    # remainder is hidden. None/0 means fully disclosed. Was previously
    # accessed by brokers/dhan/execution/order_placement.py without being
    # defined here, causing every Dhan place_order call to raise
    # AttributeError -- the field was missing, not the access being wrong.
    disclosed_quantity: int | None = None
    # ── Algo-execution parameters (populated by the ExecutionPlan planner) ──
    # Slicing algorithm to apply at the execution layer. One of
    # "NONE" / "TWAP" / "VWAP" / "ICEBERG" (see domain.orders.execution_plan).
    slicing_algo: str = "NONE"
    # Number of child slices to split `quantity` into (TWAP/VWAP/ICEBERG).
    slice_count: int = 1
    # Seconds between slices (TWAP/VWAP cadence).
    slice_interval: int = 0
    # TWAP horizon in seconds (total duration of the TWAP schedule).
    twap_duration: int | None = None
    # VWAP target participation rate as a fraction (e.g. 0.1 = 10% of volume).
    vwap_participation_rate: Decimal | None = None


@dataclass(slots=True, frozen=True)
class ModifyOrderRequest:
    """Input model for modifying an existing order."""

    order_id: str
    quantity: int | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: OrderType | None = None
    validity: Validity | None = None
    product_type: ProductType | None = None


@dataclass(slots=True, frozen=True)
class SliceOrderRequest:
    """Request for splitting a large order into child orders."""

    symbol: str = ""
    exchange: str = "NSE"
    side: Side = Side.BUY
    quantity: int = 0
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY


def expand_slice_request(
    req: SliceOrderRequest,
    slice_count: int,
    disclosed_qty: int | None = None,
) -> list[OrderRequest]:
    """Consumer path for :class:`SliceOrderRequest`.

    Splits ``req.quantity`` into ``slice_count`` child :class:`OrderRequest`
    objects. With ``disclosed_qty`` set the algo is ICEBERG (each child shows
    only ``disclosed_qty``); otherwise TWAP. Child correlation ids append a
    ``:sliceN`` suffix so each remains idempotent at the OMS.
    """
    total = max(0, req.quantity)
    if total <= 0:
        return []
    if disclosed_qty and disclosed_qty > 0:
        # ICEBERG: reveal `disclosed_qty` per slice, remainder on the last.
        disc = max(1, disclosed_qty)
        n = (total + disc - 1) // disc
        qtys = [disc] * (n - 1) + [total - disc * (n - 1)]
        algo = "ICEBERG"
        out_disc: int | None = disc
    else:
        # TWAP: split into `slice_count` equal-ish chunks.
        n = slice_count if slice_count and slice_count > 0 else 1
        base, rem = divmod(total, n)
        qtys = [base + (1 if i < rem else 0) for i in range(n)]
        algo = "TWAP"
        out_disc = None
    out: list[OrderRequest] = []
    for qty in qtys:
        if qty <= 0:
            continue
        out.append(
            OrderRequest(
                symbol=req.symbol,
                exchange=req.exchange,
                transaction_type=req.side,
                quantity=qty,
                order_type=req.order_type,
                product_type=req.product_type,
                slice=True,
                slice_count=n,
                disclosed_quantity=out_disc,
                slicing_algo=algo,
            )
        )
    return out


@dataclass(slots=True, frozen=True)
class OrderPreview:
    """Outcome of pre-flight order validation."""

    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notional: Decimal | None = None
    margin_required: Decimal | None = None


# HistoricalCandle removed — use domain.candles.historical.HistoricalBar (ADR-020).
