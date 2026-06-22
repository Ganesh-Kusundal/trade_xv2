"""Portfolio endpoints (positions, holdings, P&L)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.api.deps import get_position_manager, get_order_manager
from datalake.api.schemas import (
    PositionsResponse,
    Position,
    HoldingsResponse,
    Holding,
    PortfolioSummary,
)
from brokers.common.oms.position_manager import PositionManager
from brokers.common.oms.order_manager import OrderManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter: open, closed, all"),
    position_manager: PositionManager = Depends(get_position_manager),
):
    """Get current positions from OMS.
    
    Returns open and closed positions from broker or paper trading.
    """
    positions = position_manager.get_positions()
    
    # Filter by status if requested
    if status_filter and status_filter != "all":
        positions = [p for p in positions if (status_filter == "open") == (p.quantity != 0)]
    
    total_pnl = sum(p.unrealized_pnl + p.realized_pnl for p in positions)
    total_value = sum(abs(p.quantity) * p.avg_price for p in positions if p.quantity != 0)
    
    return PositionsResponse(
        positions=[
            Position(
                symbol=p.symbol,
                exchange=p.exchange,
                quantity=p.quantity,
                avg_price=float(p.avg_price),
                current_price=float(p.current_price) if hasattr(p, 'current_price') and p.current_price else None,
                unrealized_pnl=float(p.unrealized_pnl),
                realized_pnl=float(p.realized_pnl),
            )
            for p in positions
        ],
        count=len(positions),
        total_pnl=float(total_pnl),
        total_pnl_percent=float((total_pnl / total_value * 100) if total_value else 0.0),
    )


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings():
    """Get current holdings/portfolio.
    
    Returns long-term holdings with cost basis and current value.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Portfolio Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary():
    """Get portfolio summary with key metrics.
    
    Returns total value, P&L, margin usage, and risk metrics.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Portfolio Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.get("/pnl", response_model=dict)
async def get_pnl_history(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    group_by: str = Query("day", description="Group by: day, week, month"),
):
    """Get historical P&L curve.
    
    Returns daily/weekly/monthly P&L for equity curve visualization.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Portfolio Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )


@router.post("/square-off", response_model=dict)
async def square_off_positions(
    symbol: Optional[str] = Query(None, description="Square off specific symbol"),
):
    """Square off all or specific positions.
    
    Closes all open positions or specific symbol position.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Portfolio Management Service not connected. OMS integration in progress.",
        headers={"Retry-After": "30"},
    )
