"""Orders endpoints (orders, trades, orderbook)."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.api.deps import get_order_manager
from datalake.api.schemas import (
    OrdersResponse,
    Order,
    TradesResponse,
    Trade,
    OrderRequest,
    OrderResponse,
)
from brokers.common.oms.order_manager import OrderManager, OmsOrderCommand
from brokers.common.core.domain import Side, OrderType, ProductType

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=OrdersResponse)
async def get_orders(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter: pending, complete, cancelled, all"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max orders"),
):
    """Get order history.
    
    Returns orders from broker or paper trading with status and fills.
    """
    raise HTTPException(
        status_code=503,
        detail="Order Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.get("/trades", response_model=TradesResponse)
async def get_trades(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max trades"),
):
    """Get trade/executed order history.
    
    Returns filled trades with execution price, quantity, and brokerage.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Order Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.get("/tradebook", response_model=dict)
async def get_tradebook(
    from_date: Optional[str] = Query(None, description="Start date"),
    to_date: Optional[str] = Query(None, description="End date"),
):
    """Get complete tradebook with P&L analysis.
    
    Returns all trades with realized/unrealized P&L, win rate, etc.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Order Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.get("/{order_id}", response_model=Order)
async def get_order(order_id: str):
    """Get specific order details.
    
    Returns order with status, fills, and rejection reason if any.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Order Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.post("", response_model=OrderResponse)
async def place_order(
    req: OrderRequest,
    order_manager: OrderManager = Depends(get_order_manager),
):
    """Place a new order through the OMS.
    
    Supports market, limit, SL, SL-M order types.
    Returns order ID for tracking.
    """
    # Convert HTTP request to OMS command
    try:
        side = Side(req.transaction_type.upper())
        order_type = OrderType(req.order_type.upper())
        product_type = ProductType(req.product_type.upper()) if req.product_type else ProductType.INTRADAY
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order parameter: {exc}",
        )
    
    command = OmsOrderCommand(
        symbol=req.symbol,
        exchange=req.exchange,
        side=side,
        order_type=order_type,
        quantity=req.quantity,
        price=Decimal(str(req.price)) if req.price else Decimal("0"),
        product_type=product_type,
        correlation_id=f"http-{datetime.now().isoformat()}",
    )
    
    # Call OMS (without submit_fn — records in OMS with risk checks)
    result = order_manager.place_order(command, submit_fn=None)
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Order rejected by risk manager",
        )
    
    order = result.order
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
    )


@router.put("/{order_id}", response_model=OrderResponse)
async def modify_order(order_id: str, req: OrderRequest):
    """Modify an existing order.
    
    Updates price, quantity, or order type for pending orders.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Order Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(order_id: str):
    """Cancel a pending order.
    
    Only works for orders in PENDING or TRIGGER_PENDING status.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Order Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )
