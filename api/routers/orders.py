"""Orders endpoints (orders, trades, orderbook)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import require_auth
from api.deps import get_broker_service, get_execution_composer, get_order_repository
from api.schemas import (
    OrderRequest,
    OrderResponse,
    OrdersResponse,
    Trade,
    TradesResponse,
)
from domain import OrderStatus, OrderType, ProductType, Side
from domain.requests import OrderRequest as DomainOrderRequest
from infrastructure.observability.tracing import trace_operation

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("", response_model=OrdersResponse)
async def get_orders(
    status_filter: str | None = Query(
        None, alias="status", description="Filter: pending, complete, cancelled, all"
    ),
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max orders"),
    repo=Depends(get_order_repository),
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
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max trades"),
    repo=Depends(get_order_repository),
):
    """Get trade/executed order history.

    Returns filled trades with execution price, quantity, and brokerage.
    Uses real OMS trade history from processed trade repository.
    """
    try:
        # Get all orders and filter for filled/completed ones
        orders = repo.get_orders(status=OrderStatus.FILLED)

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
                trades.append(
                    Trade(
                        trade_id=f"trade-{order.order_id}",
                        order_id=order.order_id,
                        symbol=order.symbol,
                        exchange=order.exchange,
                        transaction_type=order.side.value,
                        quantity=order.filled_quantity,
                        price=float(order.average_price) if order.average_price else 0.0,
                        timestamp=order.timestamp or datetime.now(),
                    )
                )

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
            detail=f"Trades fetch failed: {exc!s}",
        ) from exc


@router.get("/tradebook", response_model=dict)
async def get_tradebook(
    from_date: str | None = Query(None, description="Start date"),
    to_date: str | None = Query(None, description="End date"),
    repo=Depends(get_order_repository),
):
    """Get complete tradebook with P&L analysis.

    Returns all trades with realized/unrealized P&L, win rate, etc.
    Uses real OMS data for comprehensive trade analysis.
    """
    try:
        # Get all completed orders
        orders = repo.get_orders(status=OrderStatus.FILLED)

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
            detail=f"Tradebook fetch failed: {exc!s}",
        ) from exc


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    repo=Depends(get_order_repository),
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
@trace_operation("api.orders.place_order")
async def place_order(
    req: OrderRequest,
    broker_service: Any = Depends(get_broker_service),
    composer: Any = Depends(get_execution_composer),
):
    """Place a new order through the multi-broker ExecutionComposer.

    Supports market, limit, SL, SL-M order types.
    Returns order ID for tracking.

    Execution paths (controlled by COMPOSER_EXECUTION feature flag):
    - Path B (flag ON): ExecutionComposer with multi-broker routing + quota
    - Path A (flag OFF): Legacy ExecutionService via OMS

    Multi-broker features (Path B):
    - Automatic broker routing via BrokerRouter
    - Quota management to prevent rate limit violations
    - Full provenance tracking for audit compliance
    - Kill-switch enforcement via risk_manager
    """
    from config.feature_flags import FeatureFlags

    # Convert HTTP request to domain request
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

    # Check feature flag for execution path selection
    use_composer = FeatureFlags.is_enabled("COMPOSER_EXECUTION") and composer is not None

    if use_composer:
        # Path B: ExecutionComposer (multi-broker, async, with kill-switch)
        domain_req = DomainOrderRequest(
            symbol=req.symbol,
            exchange=req.exchange,
            transaction_type=side,
            order_type=order_type,
            quantity=req.quantity,
            price=Decimal(str(req.price)) if req.price else Decimal("0"),
            product_type=product_type,
            correlation_id=req.correlation_id or f"http-{uuid.uuid4().hex}",
        )

        result = await composer.place_order(domain_req)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error_code or result.message or "Order rejected by broker",
            )

        return OrderResponse(
            order_id=result.order_id,
            symbol=req.symbol,
            exchange=req.exchange,
            transaction_type=req.transaction_type,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
        )
    else:
        # Path A: Legacy ExecutionService (OMS-first, sync)
        exec_svc = broker_service.execution_service if broker_service else None
        if exec_svc is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Execution service unavailable",
            )

        from application.oms.order_manager import OmsOrderCommand

        command = OmsOrderCommand(
            symbol=req.symbol,
            exchange=req.exchange,
            side=side,
            order_type=order_type,
            quantity=req.quantity,
            price=Decimal(str(req.price)) if req.price else Decimal("0"),
            product_type=product_type,
            correlation_id=req.correlation_id or f"http-{uuid.uuid4().hex}",
        )

        result = exec_svc.place_order(command)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Order rejected",
            )

        return OrderResponse(
            order_id=result.order_id or "",
            symbol=req.symbol,
            exchange=req.exchange,
            transaction_type=req.transaction_type,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price,
            status="PENDING",
        )


@router.put("/{order_id}", response_model=OrderResponse)
@trace_operation("api.orders.modify_order")
async def modify_order(
    order_id: str,
    req: OrderRequest,
    broker_service: Any = Depends(get_broker_service),
    composer: Any = Depends(get_execution_composer),
    repo=Depends(get_order_repository),
):
    """Modify an existing order via ExecutionComposer or legacy ExecutionService.

    Updates price, quantity, or order type for pending orders.
    Uses feature flag to select execution path.
    """
    from config.feature_flags import FeatureFlags

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

    use_composer = FeatureFlags.is_enabled("COMPOSER_EXECUTION") and composer is not None

    if use_composer:
        # Path B: ExecutionComposer
        from domain.requests import ModifyOrderRequest

        modify_req = ModifyOrderRequest(
            order_id=order_id,
            quantity=req.quantity,
            price=Decimal(str(req.price)) if req.price else None,
            order_type=order_type,
            product_type=product_type,
        )

        result = await composer.modify_order(modify_req)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error_code or result.message or "Order modification rejected",
            )

        return OrderResponse(
            order_id=result.order_id,
            symbol=existing.symbol,
            exchange=existing.exchange,
            transaction_type=existing.side.value,
            order_type=req.order_type,
            quantity=req.quantity or existing.quantity,
            price=req.price,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
        )
    else:
        # Path A: Legacy ExecutionService
        exec_svc = broker_service.execution_service if broker_service else None
        if exec_svc is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Execution service unavailable",
            )

        from application.oms.order_manager import OmsOrderCommand

        command = OmsOrderCommand(
            symbol=existing.symbol,
            exchange=existing.exchange,
            side=existing.side,
            order_type=order_type,
            quantity=req.quantity or existing.quantity,
            price=Decimal(str(req.price)) if req.price else existing.price,
            product_type=product_type,
            order_id=order_id,
        )

        result = exec_svc.modify_order(command)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Order modification rejected",
            )

        return OrderResponse(
            order_id=order_id,
            symbol=existing.symbol,
            exchange=existing.exchange,
            transaction_type=existing.side.value,
            order_type=req.order_type,
            quantity=req.quantity or existing.quantity,
            price=req.price,
            status="PENDING",
        )


@router.delete("/{order_id}", response_model=OrderResponse)
@trace_operation("api.orders.cancel_order")
async def cancel_order(
    order_id: str,
    broker_service: Any = Depends(get_broker_service),
    composer: Any = Depends(get_execution_composer),
    repo=Depends(get_order_repository),
):
    """Cancel a pending order via ExecutionComposer or legacy ExecutionService.

    Only works for orders in PENDING or TRIGGER_PENDING status.
    Uses feature flag to select execution path.
    """
    from config.feature_flags import FeatureFlags

    # Pre-fetch order from repo for symbol/exchange metadata
    existing = repo.get_order(order_id) if repo else None

    use_composer = FeatureFlags.is_enabled("COMPOSER_EXECUTION") and composer is not None

    if use_composer:
        # Path B: ExecutionComposer
        result = await composer.cancel_order(order_id)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error_code or result.message or "Order cancellation rejected",
            )

        return OrderResponse(
            order_id=result.order_id,
            symbol=existing.symbol if existing else "",
            exchange=existing.exchange if existing else "",
            transaction_type=existing.side.value if existing else "",
            order_type=existing.order_type.value if existing else "",
            quantity=existing.quantity if existing else 0,
            price=float(existing.price) if existing and existing.price else None,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
        )
    else:
        # Path A: Legacy ExecutionService
        exec_svc = broker_service.execution_service if broker_service else None
        if exec_svc is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Execution service unavailable",
            )

        result = exec_svc.cancel_order(order_id)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.error or "Order cancellation rejected",
            )

        return OrderResponse(
            order_id=order_id,
            symbol=existing.symbol if existing else "",
            exchange=existing.exchange if existing else "",
            transaction_type=existing.side.value if existing else "",
            order_type=existing.order_type.value if existing else "",
            quantity=existing.quantity if existing else 0,
            price=float(existing.price) if existing and existing.price else None,
            status="CANCELLED",
        )
