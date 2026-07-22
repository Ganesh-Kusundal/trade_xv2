"""Orders endpoints (orders, trades, orderbook)."""

import asyncio
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
)
from domain.orders.requests import OrderRequest as DomainOrderRequest
from domain.ports.async_bridge import run_coro_sync
from infrastructure.observability.tracing import trace_operation
from interface.api.auth import require_auth
from interface.api.deps import (
    enforce_live_order_authority,
    get_execution_composer,
    get_order_manager,
)
from interface.api.schemas import (
    OrderRequest,
    OrderResponse,
    OrdersResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])

# Include trade endpoints as sub-router
from interface.api.routers._trades import router as trades_router

router.include_router(trades_router, prefix="/trades", tags=["trades"])


from domain.ports.time_service import get_current_clock


def _order_timestamp(order: Any) -> datetime:
    """OMS orders may lack timestamp; schema requires datetime (not None)."""
    ts = getattr(order, "timestamp", None)
    return ts if ts is not None else get_current_clock().now()


@router.get("", response_model=OrdersResponse)
async def get_orders(
    status_filter: str | None = Query(
        None, alias="status", description="Filter: pending, complete, cancelled, all"
    ),
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max orders"),
    om=Depends(get_order_manager),
):
    """Get order history from OMS."""
    # Parse optional status filter
    status = None
    if status_filter and status_filter != "all":
        try:
            status = OrderStatus(status_filter.upper())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {status_filter}"
            ) from None

    orders = om.get_orders(status=status)

    # Apply date filters if provided
    if from_date:
        from_dt = datetime.fromisoformat(from_date)
        orders = [o for o in orders if o.timestamp and o.timestamp >= from_dt]
    if to_date:
        to_dt = datetime.fromisoformat(to_date)
        orders = [o for o in orders if o.timestamp and o.timestamp <= to_dt]

    # Limit results
    orders = orders[:limit]

    return OrdersResponse(
        orders=[
            OrderResponse(
                order_id=o.order_id,
                symbol=o.symbol,
                exchange=o.exchange,
                transaction_type=o.side.value,
                order_type=o.order_type.value,
                quantity=o.quantity,
                price=float(o.price) if o.price else None,
                status=o.status.value,
                filled_quantity=o.filled_quantity,
                average_price=float(o.average_price) if o.average_price else None,
                timestamp=_order_timestamp(o),
            )
            for o in orders
        ],
        count=len(orders),
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    om=Depends(get_order_manager),
):
    """Get specific order details from OMS."""
    order = om.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )
    return OrderResponse(
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        transaction_type=order.side.value,
        order_type=order.order_type.value,
        quantity=order.quantity,
        price=float(order.price) if order.price else None,
        status=order.status.value,
        filled_quantity=order.filled_quantity,
        average_price=float(order.average_price) if order.average_price else None,
        timestamp=_order_timestamp(order),
    )


def _resolve_api_broker() -> str:
    """Server-side broker selection — clients cannot override via query param."""
    from config.schema import load_trading_config

    return load_trading_config().primary_broker


def _api_to_domain_order_request(
    req: OrderRequest,
    *,
    side: Side,
    order_type: OrderType,
    product_type: ProductType,
) -> DomainOrderRequest:
    """Map API schema → domain OrderRequest for ExecutionComposer."""
    price = Decimal(str(req.price)) if req.price else Decimal("0")
    if order_type == OrderType.MARKET:
        price = Decimal("0")
    trigger = Decimal(str(req.trigger_price)) if req.trigger_price else None
    return DomainOrderRequest(
        symbol=req.symbol,
        exchange=req.exchange or "NSE",
        transaction_type=side,
        quantity=req.quantity,
        price=price,
        trigger_price=trigger,
        order_type=order_type,
        product_type=product_type,
        correlation_id=req.correlation_id or f"api:{uuid.uuid4().hex[:12]}",
    )


@router.post("", response_model=OrderResponse)
@trace_operation("interface.api.orders.place_order")
async def place_order(
    req: OrderRequest,
    composer: Any = Depends(get_execution_composer),
):
    """Place a new order via process ExecutionComposer + OMS spine.

    Path: API → live authority gate → ExecutionComposer → OMS → broker.
    Broker is resolved from server ``TRADEX_PRIMARY_BROKER`` / trading config
    (not from client input). Uses the process session wired at startup (ADR-0020).
    """
    broker = _resolve_api_broker()

    try:
        side = Side(req.transaction_type.upper())
        order_type = OrderType(req.order_type.upper())
        product_type = (
            ProductType(req.product_type.upper()) if req.product_type else ProductType.INTRADAY
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order parameter: {exc}",
        ) from exc

    enforce_live_order_authority(
        mutation_action="place",
        risk_payload={
            "symbol": req.symbol,
            "exchange": req.exchange or "NSE",
            "side": req.transaction_type.upper(),
            "order_type": req.order_type.upper(),
            "quantity": req.quantity,
            "price": req.price or "0",
            "product_type": (req.product_type or product_type.value).upper(),
        },
    )

    domain_req = _api_to_domain_order_request(
        req, side=side, order_type=order_type, product_type=product_type
    )

    try:
        response = await composer.place_order(domain_req, broker_id=broker)
    except Exception as exc:
        logger.exception("place_order failed via ExecutionComposer")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not getattr(response, "success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=getattr(response, "message", None) or "Order rejected by OMS/risk/broker",
        )

    status_val = getattr(getattr(response, "status", None), "value", None) or str(
        getattr(response, "status", "OPEN")
    )
    return OrderResponse(
        order_id=getattr(response, "order_id", "") or "",
        symbol=req.symbol,
        exchange=req.exchange,
        transaction_type=req.transaction_type,
        order_type=req.order_type,
        quantity=req.quantity,
        price=req.price,
        status=status_val,
    )


@router.put("/{order_id}", response_model=OrderResponse)
@trace_operation("interface.api.orders.modify_order")
async def modify_order(
    order_id: str,
    req: OrderRequest,
    composer: Any = Depends(get_execution_composer),
    om=Depends(get_order_manager),
):
    """Modify an existing order through the OMS singleton.

    Phase 2: routes modify through the shared OrderManager (single owner of
    order state + idempotency) but uses the ExecutionComposer only as the
    transport (broker routing/quota). The OMS kill-switch guards the mutation.
    """

    try:
        Side(req.transaction_type.upper())
        order_type = OrderType(req.order_type.upper())
        product_type = (
            ProductType(req.product_type.upper()) if req.product_type else ProductType.INTRADAY
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order parameter: {exc}",
        ) from exc

    existing = om.get_order(order_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )
    if existing.status.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify order in terminal state: {existing.status.value}",
        )

    enforce_live_order_authority(
        mutation_action="modify",
        risk_payload={
            "symbol": req.symbol,
            "exchange": req.exchange or existing.exchange,
            "side": req.transaction_type.upper(),
            "order_type": req.order_type.upper(),
            "quantity": req.quantity,
            "price": req.price or (float(existing.price) if existing.price else "0"),
            "product_type": (req.product_type or existing.product_type.value).upper(),
        },
    )

    from domain.orders.requests import ModifyOrderRequest

    modify_req = ModifyOrderRequest(
        order_id=order_id,
        quantity=req.quantity,
        price=Decimal(str(req.price)) if req.price else None,
        order_type=order_type,
        product_type=product_type,
    )

    def modify_fn(r: ModifyOrderRequest) -> Any:
        return run_coro_sync(composer.modify_order(r))

    result = await asyncio.to_thread(om.modify_order, modify_req, modify_fn=modify_fn)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Order modification rejected",
        )

    order = result.order or existing
    return OrderResponse(
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        transaction_type=order.side.value,
        order_type=order.order_type.value,
        quantity=order.quantity,
        price=float(order.price) if order.price else None,
        status=order.status.value,
    )


@router.delete("/{order_id}", response_model=OrderResponse)
@trace_operation("interface.api.orders.cancel_order")
async def cancel_order(
    order_id: str,
    composer: Any = Depends(get_execution_composer),
    om=Depends(get_order_manager),
):
    """Cancel a pending order through the OMS singleton.

    Only works for orders in PENDING or TRIGGER_PENDING status. Routes through
    the shared OrderManager (kill-switch guarded) using the composer as transport.
    """

    existing = om.get_order(order_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    enforce_live_order_authority(mutation_action="cancel")

    def cancel_fn(oid: str) -> bool:
        response = run_coro_sync(composer.cancel_order(oid))
        return bool(getattr(response, "success", False))

    result = await asyncio.to_thread(om.cancel_order, order_id, cancel_fn=cancel_fn)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Order cancellation rejected",
        )

    order = result.order or existing
    return OrderResponse(
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        transaction_type=order.side.value,
        order_type=order.order_type.value,
        quantity=order.quantity,
        price=float(order.price) if order.price else None,
        status=order.status.value,
    )
