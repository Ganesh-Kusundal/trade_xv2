"""Trade-related endpoints (trades, tradebook)."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.deps import get_order_manager, get_position_manager
from interface.api.schemas import TradeResponse, TradesResponse
from domain import OrderStatus
from domain.ports.time_service import get_current_clock

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=TradesResponse)
async def get_trades(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Max trades"),
    om=Depends(get_order_manager),
):
    """Get trade/executed order history.

    Returns filled trades with execution price, quantity, and brokerage.
    Uses real OMS trade history from processed trade repository.
    """
    try:
        # Get all orders and filter for filled/completed ones
        orders = om.get_orders(status=OrderStatus.FILLED)

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
                        timestamp=order.timestamp or get_current_clock().now(),
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
    om=Depends(get_order_manager),
    position_manager=Depends(get_position_manager),
):
    """Get complete tradebook with P&L analysis.

    P&L is sourced from the single PositionManager (the authoritative book
    that fills update), NOT recomputed per-request from a divergent source.
    """
    try:
        orders = om.get_orders(status=OrderStatus.FILLED)

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
