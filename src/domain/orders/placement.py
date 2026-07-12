"""Shared order placement helpers — single intent builder for Session and Instrument.

KD-4 / KD-9: Instrument uses OrderServicePort only; Session may keep EP legacy.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.enums import OrderType, ProductType, Side
from domain.orders.execution_plan import (
    ExecutionPlan,
    PlanContext,
    SlicingAlgo,
    SlicingPlan,
)
from domain.orders.intent import OrderIntent
from domain.orders.requests import OrderRequest, SliceOrderRequest, expand_slice_request

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument
    from domain.models.trading import SignalDTO
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import OrderResult


def build_execution_plan(
    signal: SignalDTO,
    ctx: PlanContext,
) -> ExecutionPlan:
    """Build an :class:`ExecutionPlan` from a signal + runtime context.

    Thin façade over :meth:`ExecutionPlan.from_signal` so the application
    layer has a single, named entry point for plan construction.
    """
    return ExecutionPlan.from_signal(signal, ctx)


def plan_to_intents(plan: ExecutionPlan) -> list[OrderIntent]:
    """Expand a plan into the concrete :class:`OrderIntent` list to submit.

    With ``slicing.algo == NONE`` this is a 1:1 mapping of the plan's legs.
    For TWAP/VWAP/ICEBERG the aggregate quantity is split per
    :meth:`ExecutionPlan.sliced_quantities` into stable, idempotent child
    intents (each appends ``:sliceN`` to its correlation id).
    """
    if plan.slicing.algo == SlicingAlgo.NONE or not plan.legs:
        return plan.to_intents()

    slices = plan.sliced_quantities()
    out: list[OrderIntent] = []
    for leg in plan.legs:
        for i, qty in enumerate(slices):
            if qty <= 0:
                continue
            base_cid = leg.correlation_id
            cid = f"{base_cid}:slice{i + 1}" if base_cid else None
            out.append(replace(leg, quantity=qty, correlation_id=cid))
    return out


def plan_to_order_requests(plan: ExecutionPlan) -> list[OrderRequest]:
    """Materialize a plan's legs into algo-aware :class:`OrderRequest` objects.

    Carries the slicing parameters (algo, slice_count, interval, disclosed
    qty, TWAP/VWAP fields) so downstream broker adapters have everything they
    need to execute the plan.
    """
    out: list[OrderRequest] = []
    for intent in plan.to_intents():
        out.append(
            OrderRequest(
                symbol=intent.symbol,
                exchange=intent.exchange,
                transaction_type=intent.side,
                quantity=intent.quantity,
                price=intent.price,
                order_type=intent.order_type,
                product_type=intent.product_type,
                correlation_id=intent.correlation_id,
                slice=plan.slicing.algo != SlicingAlgo.NONE,
                slice_count=plan.slicing.slice_count,
                slice_interval=plan.slicing.interval_seconds,
                twap_duration=plan.slicing.twap_duration_seconds,
                vwap_participation_rate=plan.slicing.vwap_participation_rate,
                slicing_algo=plan.slicing.algo.value,
                disclosed_quantity=plan.slicing.disclosed_qty,
            )
        )
    return out


def slice_order_request(
    req: SliceOrderRequest,
    plan: SlicingPlan,
) -> list[OrderRequest]:
    """Consumer path for a :class:`SliceOrderRequest` driven by a slicing plan."""
    return expand_slice_request(req, plan.slice_count, plan.disclosed_qty)


def build_order_intent(
    instrument: Instrument,
    side: Side,
    quantity: int,
    *,
    price: Decimal | None = None,
    order_type: OrderType = OrderType.LIMIT,
    product_type: ProductType = ProductType.INTRADAY,
    trigger_price: Decimal | None = None,
    correlation_id: str | None = None,
) -> OrderIntent:
    """Build a domain :class:`OrderIntent` from an instrument + order params."""
    kwargs: dict = {
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "side": side,
        "quantity": quantity,
        "price": price if price is not None else Decimal("0"),
        "order_type": order_type,
        "product_type": product_type,
        "trigger_price": trigger_price,
    }
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id
    return OrderIntent(**kwargs)


def place_via_order_service(
    order_service: OrderServicePort,
    intent: OrderIntent,
) -> OrderResult:
    """Submit intent through OMS (risk + book + execution)."""
    return order_service.place(intent)


__all__ = [
    "build_execution_plan",
    "build_order_intent",
    "place_via_order_service",
    "plan_to_intents",
    "plan_to_order_requests",
    "slice_order_request",
]
