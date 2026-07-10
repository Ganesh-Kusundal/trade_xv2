"""Orders endpoints (orders, trades, orderbook)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.auth import require_auth
from interface.api.deps import get_execution_composer, get_order_repository, get_position_manager
from interface.api.schemas import (
    OrderRequest,
    OrderResponse,
    OrdersResponse,
    TradeResponse,
    TradesResponse,
)
from domain import OrderStatus, OrderType, ProductType, Side
from domain.orders.requests import OrderRequest as DomainOrderRequest
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
                    TradeResponse(
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
    position_manager=Depends(get_position_manager),
):
    """Get complete tradebook with P&L analysis.

    P&L is sourced from the single PositionManager (the authoritative book
    that fills update), NOT recomputed per-request from a divergent source.
    """
    try:
        orders = repo.get_orders(status=OrderStatus.FILLED)

        if from_date:
            from_dt = datetime.fromisoformat(from_date)
            orders = [o for o in orders if o.timestamp and o.timestamp >= from_dt]
        if to_date:
            to_dt = datetime.fromisoformat(to_date)
            orders = [o for o in orders if o.timestamp and o.timestamp <= to_dt]

        total_trades = len(orders)
        filled_orders = [o for o in orders if o.filled_quantity > 0]

        # Single source of truth: positions held by the shared PositionManager.
        pnl_by_symbol: dict[str, float] = {}
        realized_total = 0.0
        unrealized_total = 0.0
        if position_manager is not None:
            positions = position_manager.get_positions()
            for pos in positions:
                pnl_by_symbol[pos.symbol] = float(getattr(pos, "realized_pnl", 0.0))
                realized_total += float(getattr(pos, "realized_pnl", 0.0))
                unrealized_total += float(getattr(pos, "unrealized_pnl", 0.0))

        total_pnl = realized_total
        winning_trades = 0
        losing_trades = 0

        for order in filled_orders:
            pnl = pnl_by_symbol.get(order.symbol, 0.0)
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
                "realized_pnl": realized_total,
                "unrealized_pnl": unrealized_total,
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


def _resolve_api_broker() -> str:
    """Server-side broker selection — clients cannot override via query param."""
    from config.schema import load_trading_config

    return load_trading_config().primary_broker


@router.post("", response_model=OrderResponse)
@trace_operation("interface.api.orders.place_order")
async def place_order(
    req: OrderRequest,
):
    """Place a new order via institutional OMS spine (tradex.connect).

    Path: OrderIntent → Risk → OMS → ExecutionProvider.
    Broker is resolved from server ``TRADEX_PRIMARY_BROKER`` / trading config
    (not from client input).

    The order is admitted through the process-wide OMS singleton (registered
    by the composition root), so fills land in the SAME book that
    ``GET /orders`` and ``GET /tradebook`` later query. ``correlation_id``
    from the request is forwarded for idempotency (prevents duplicate orders
    on client retry).
    """
    import tradex

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

    session = tradex.connect(broker)
    try:
        instrument = session.universe.equity(req.symbol, exchange=req.exchange or "NSE")
        px = Decimal(str(req.price)) if req.price else None
        trigger_px = Decimal(str(req.trigger_price)) if req.trigger_price else None
        if order_type == OrderType.MARKET:
            px = None
        intent = session.intent(
            instrument,
            side,
            req.quantity,
            price=px,
            trigger_price=trigger_px,
            order_type=order_type,
            product_type=product_type,
            correlation_id=req.correlation_id or f"api:{uuid.uuid4().hex[:12]}",
        )
        result = session.place(intent)
    finally:
        # Do NOT discard the OMS on close: tradex.connect now resolves the
        # process-wide singleton. session.close() only clears the per-session
        # default provider registration.
        session.close()

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Order rejected by OMS/risk/broker",
        )

    order = result.order
    status_val = getattr(getattr(order, "status", None), "value", None) or str(
        getattr(order, "status", "OPEN")
    )
    return OrderResponse(
        order_id=getattr(order, "order_id", "") or "",
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
    repo=Depends(get_order_repository),
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

    from domain.orders.requests import ModifyOrderRequest

    modify_req = ModifyOrderRequest(
        order_id=order_id,
        quantity=req.quantity,
        price=Decimal(str(req.price)) if req.price else None,
        order_type=order_type,
        product_type=product_type,
    )

    order_manager = repo._oms if hasattr(repo, "_oms") else None
    if order_manager is None:
        # repo may be an adapter; fall back to the process-wide OMS singleton.
        from application.oms import get_oms_context

        ctx = get_oms_context()
        order_manager = ctx.order_manager if ctx is not None else None

    if order_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OMS not initialized; cannot modify order.",
        )

    # Composer is transport-only: build the broker modify call.
    async def modify_fn(r: ModifyOrderRequest) -> Any:
        return await composer.modify_order(r)

    result = order_manager.modify_order(modify_req, modify_fn=modify_fn)

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
    repo=Depends(get_order_repository),
):
    """Cancel a pending order through the OMS singleton.

    Only works for orders in PENDING or TRIGGER_PENDING status. Routes through
    the shared OrderManager (kill-switch guarded) using the composer as transport.
    """

    existing = repo.get_order(order_id) if repo else None
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )

    order_manager = repo._oms if hasattr(repo, "_oms") else None
    if order_manager is None:
        from application.oms import get_oms_context

        ctx = get_oms_context()
        order_manager = ctx.order_manager if ctx is not None else None

    if order_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OMS not initialized; cannot cancel order.",
        )

    async def cancel_fn(oid: str) -> bool:
        response = await composer.cancel_order(oid)
        return bool(getattr(response, "success", False))

    result = order_manager.cancel_order(order_id, cancel_fn=cancel_fn)

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
