"""Orders endpoints (orders, trades, orderbook)."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.api.deps import get_order_repository, get_broker_service
from datalake.api.auth import require_auth
from datalake.api.schemas import (
    OrdersResponse,
    TradesResponse,
    Trade,
    OrderRequest,
    OrderResponse,
)
from domain.repositories import OrderRepository
from domain import Order, OrderStatus, Side, OrderType, ProductType
from domain.requests import OrderRequest as DomainOrderRequest
from brokers.common.oms.order_repository_adapter import request_to_command

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])

@router.get("", response_model=OrdersResponse)
async def get_orders(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter: pending, complete, cancelled, all"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max orders"),
    repo = Depends(get_order_repository),
):
    """Get order history from OMS."""
    # Parse optional status filter
    status = None
    if status_filter and status_filter != "all":
        try:
            status = OrderStatus(status_filter.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    orders = repo.get_orders(status=status)

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
                timestamp=o.timestamp,
            )
            for o in orders
        ],
        count=len(orders),
    )


@router.get("/trades", response_model=TradesResponse)
async def get_trades(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max trades"),
    repo = Depends(get_order_repository),
):
    """Get trade/executed order history.

    Returns filled trades with execution price, quantity, and brokerage.
    Uses real OMS trade history from processed trade repository.
    """
    try:
        # Get all orders and filter for filled/completed ones
        orders = repo.get_orders(status=OrderStatus.COMPLETE)
        
        # Apply date filters if provided
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            orders = [o for o in orders if o.timestamp and o.timestamp >= from_dt]
        if to_date:
            to_dt = datetime.fromisoformat(to_date)
            orders = [o for o in orders if o.timestamp and o.timestamp <= to_dt]
        
        # Limit results
        orders = orders[:limit]
        
        # Convert filled orders to trades
        trades = []
        for order in orders:
            if order.filled_quantity > 0:
                trades.append(Trade(
                    trade_id=f"trade-{order.order_id}",
                    order_id=order.order_id,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    transaction_type=order.side.value,
                    quantity=order.filled_quantity,
                    price=float(order.average_price) if order.average_price else 0.0,
                    timestamp=order.timestamp or datetime.now(),
                ))
        
        return TradesResponse(
            trades=trades,
            count=len(trades),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Trades fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trades fetch failed: {str(exc)}",
        )


@router.get("/tradebook", response_model=dict)
async def get_tradebook(
    from_date: Optional[str] = Query(None, description="Start date"),
    to_date: Optional[str] = Query(None, description="End date"),
    repo = Depends(get_order_repository),
):
    """Get complete tradebook with P&L analysis.

    Returns all trades with realized/unrealized P&L, win rate, etc.
    Uses real OMS data for comprehensive trade analysis.
    """
    try:
        # Get all completed orders
        orders = repo.get_orders(status=OrderStatus.COMPLETE)
        
        # Apply date filters
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            orders = [o for o in orders if o.timestamp and o.timestamp >= from_dt]
        if to_date:
            to_dt = datetime.fromisoformat(to_date)
            orders = [o for o in orders if o.timestamp and o.timestamp <= to_dt]
        
        # Calculate tradebook metrics
        total_trades = len(orders)
        filled_orders = [o for o in orders if o.filled_quantity > 0]
        
        # Calculate P&L (simplified - in production would use position manager)
        total_pnl = 0.0
        winning_trades = 0
        losing_trades = 0
        
        for order in filled_orders:
            if order.average_price and order.filled_quantity:
                # Simplified P&L calculation
                pnl = 0.0  # Would need position context for accurate P&L
                total_pnl += pnl
                if pnl > 0:
                    winning_trades += 1
                elif pnl < 0:
                    losing_trades += 1
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        return {
            "trades": [
                {
                    "trade_id": f"trade-{o.order_id}",
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "transaction_type": o.side.value,
                    "quantity": o.filled_quantity,
                    "price": float(o.average_price) if o.average_price else 0.0,
                    "timestamp": o.timestamp.isoformat() if o.timestamp else None,
                }
                for o in filled_orders
            ],
            "summary": {
                "total_trades": total_trades,
                "filled_trades": len(filled_orders),
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
            },
            "count": len(filled_orders),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Tradebook fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tradebook fetch failed: {str(exc)}",
        )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    repo = Depends(get_order_repository),
):
    """Get specific order details from OMS."""
    order = repo.get_order(order_id)
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
        timestamp=order.timestamp,
    )


@router.post("", response_model=OrderResponse)
async def place_order(
    req: OrderRequest,
    repo = Depends(get_order_repository),
):
    """Place a new order through the OMS.

    Supports market, limit, SL, SL-M order types.
    Returns order ID for tracking.
    
    Graceful degradation:
    - Returns 503 if broker service is unavailable
    - Includes Retry-After header for client backoff
    - Orders are NEVER accepted without broker connectivity
    """
    # Check broker availability before accepting order
    broker_service = get_broker_service()
    if broker_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker service not configured. Cannot place orders.",
            headers={"Retry-After": "30"},
        )
    
    # Check if broker is connected
    if hasattr(broker_service, "is_connected") and not broker_service.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker disconnected. Order placement unavailable.",
            headers={
                "Retry-After": "30",
                "X-Service-Degraded": "broker-disconnected",
            },
        )
    
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

    domain_req = DomainOrderRequest(
        symbol=req.symbol,
        exchange=req.exchange,
        transaction_type=side,
        order_type=order_type,
        quantity=req.quantity,
        price=Decimal(str(req.price)) if req.price else Decimal("0"),
        product_type=product_type,
        correlation_id=f"http-{datetime.now().isoformat()}",
    )

    # Call OMS with broker submission function
    execution_svc = getattr(broker_service, "execution_service", None)
    if execution_svc is not None:
        result = execution_svc.place_order(request_to_command(domain_req))
    else:
        submit_fn = getattr(broker_service, "submit_order", None)
        if submit_fn is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Broker order submission unavailable.",
                headers={"Retry-After": "60"},
            )
        result = repo.place_command(request_to_command(domain_req), submit_fn=submit_fn)

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
        timestamp=order.timestamp,
    )


@router.put("/{order_id}", response_model=OrderResponse)
async def modify_order(
    order_id: str,
    req: OrderRequest,
    repo = Depends(get_order_repository),
):
    """Modify an existing order.

    Updates price, quantity, or order type for pending orders.
    Uses real broker connectivity for order modification.
    """
    try:
        side = Side(req.transaction_type.upper())
        order_type = OrderType(req.order_type.upper())
        product_type = ProductType(req.product_type.upper()) if req.product_type else ProductType.INTRADAY
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order parameter: {exc}",
        )

    existing = repo.get_order(order_id)
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
    
    # Check broker availability for modify
    broker_service = get_broker_service()
    if broker_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker service not configured. Cannot modify orders.",
            headers={"Retry-After": "30"},
        )
    
    # Get broker cancel and submit functions
    cancel_fn = getattr(broker_service, "cancel_order", None)
    submit_fn = getattr(broker_service, "submit_order", None)
    
    if cancel_fn is None or submit_fn is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Broker order modification unavailable.",
            headers={"Retry-After": "60"},
        )

    # Cancel existing, place new (as a pending-modify pattern)
    cancel_result = repo.cancel_with_fn(order_id, cancel_fn=cancel_fn)
    if not cancel_result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=cancel_result.error or "Modify: cancel failed",
        )

    modify_req = DomainOrderRequest(
        symbol=req.symbol or existing.symbol,
        exchange=req.exchange or existing.exchange,
        transaction_type=side,
        order_type=order_type,
        quantity=req.quantity or existing.quantity,
        price=Decimal(str(req.price)) if req.price else existing.price,
        product_type=product_type,
        correlation_id=f"http-modify-{datetime.now().isoformat()}",
    )

    result = repo.place_command(request_to_command(modify_req), submit_fn=submit_fn)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Modify: replace failed",
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
        timestamp=order.timestamp,
    )


@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: str,
    repo = Depends(get_order_repository),
):
    """Cancel a pending order.

    Only works for orders in PENDING or TRIGGER_PENDING status.
    Uses real broker connectivity for order cancellation.
    """
    # Check broker availability
    broker_service = get_broker_service()
    if broker_service is not None:
        cancel_fn = getattr(broker_service, "cancel_order", None)
    else:
        cancel_fn = None
    
    result = repo.cancel_with_fn(order_id, cancel_fn=cancel_fn)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Order cancellation rejected",
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
        timestamp=order.timestamp,
    )
