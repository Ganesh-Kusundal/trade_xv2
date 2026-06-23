"""Portfolio endpoints (positions, holdings, P&L)."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.api.deps import (
    get_position_repository,
    get_order_repository,
    get_risk_manager,
    get_broker_service,
    get_trade_journal,
)
from datalake.api.auth import require_auth
from datalake.api.schemas import (
    PositionsResponse,
    Position,
    HoldingsResponse,
    Holding,
    PortfolioSummary,
)
from domain.repositories import PositionRepository
from domain import Side, OrderType, ProductType

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter: open, closed, all"),
    position_repo: PositionRepository = Depends(get_position_repository),
):
    """Get current positions from OMS.
    
    Returns open and closed positions from broker or paper trading.
    """
    positions = position_repo.get_positions()
    
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
                average_price=float(p.avg_price),
                current_price=float(getattr(p, 'ltp', Decimal('0'))),
                unrealized_pnl=float(p.unrealized_pnl),
                realized_pnl=float(p.realized_pnl),
                pnl_pct=float((p.unrealized_pnl + p.realized_pnl) / (abs(p.avg_price) * abs(p.quantity)) * 100) if p.avg_price and p.quantity else 0.0,
            )
            for p in positions
        ],
        count=len(positions),
        total_pnl=float(total_pnl),
        total_pnl_percent=float((total_pnl / total_value * 100) if total_value else 0.0),
    )


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings(
    position_repo: PositionRepository = Depends(get_position_repository),
):
    """Get current holdings/portfolio.
    
    Returns long-term holdings with cost basis and current value.
    Uses real PositionManager data, filtering for delivery positions.
    """
    try:
        positions = position_repo.get_positions()
        
        # Filter for holdings (non-zero quantity positions)
        holdings = []
        total_value = 0.0
        total_invested = 0.0
        total_pnl = 0.0
        
        for p in positions:
            if p.quantity != 0:
                current_price = float(getattr(p, 'ltp', Decimal('0')))
                avg_price = float(p.avg_price)
                quantity = abs(p.quantity)
                
                invested = quantity * avg_price
                current = quantity * current_price
                pnl = current - invested
                
                holdings.append(Holding(
                    symbol=p.symbol,
                    exchange=p.exchange,
                    quantity=quantity,
                    average_price=avg_price,
                    current_price=current_price,
                    invested_value=invested,
                    current_value=current,
                    pnl=pnl,
                    pnl_percent=(pnl / invested * 100) if invested > 0 else 0.0,
                ))
                
                total_value += current
                total_invested += invested
                total_pnl += pnl
        
        return HoldingsResponse(
            holdings=holdings,
            count=len(holdings),
            total_value=total_value,
            total_invested=total_invested,
            total_pnl=total_pnl,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Holdings fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Holdings fetch failed: {str(exc)}",
        )


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    position_repo: PositionRepository = Depends(get_position_repository),
    risk_manager = Depends(get_risk_manager),
):
    """Get portfolio summary with key metrics.
    
    Returns total value, P&L, margin usage, and risk metrics.
    Uses real PositionManager and RiskManager data.
    """
    try:
        positions = position_repo.get_positions()
        
        # Calculate portfolio metrics
        total_value = 0.0
        total_invested = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        positions_count = 0
        holdings_count = 0
        
        for p in positions:
            if p.quantity != 0:
                current_price = float(getattr(p, 'ltp', Decimal('0')))
                avg_price = float(p.avg_price)
                quantity = abs(p.quantity)
                
                invested = quantity * avg_price
                current = quantity * current_price
                pnl = current - invested
                
                total_value += current
                total_invested += invested
                
                # Split P&L into realized and unrealized
                realized_pnl += float(p.realized_pnl)
                unrealized_pnl += float(p.unrealized_pnl)
                
                positions_count += 1
                if quantity > 0:  # Long positions
                    holdings_count += 1
        
        total_pnl = realized_pnl + unrealized_pnl
        total_pnl_percent = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        
        # Get margin info from risk manager
        margin_used = 0.0
        margin_available = 0.0
        if risk_manager:
            try:
                # Try to get capital info from risk manager
                capital = float(risk_manager.capital_fn()) if hasattr(risk_manager, 'capital_fn') else 0.0
                margin_available = capital - margin_used
            except Exception:
                margin_available = 0.0
        
        return PortfolioSummary(
            total_value=total_value,
            total_invested=total_invested,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            margin_used=margin_used,
            margin_available=margin_available,
            positions_count=positions_count,
            holdings_count=holdings_count,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Portfolio summary fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Portfolio summary fetch failed: {str(exc)}",
        )


@router.get("/pnl", response_model=dict)
async def get_pnl_history(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    group_by: str = Query("day", description="Group by: day, week, month"),
    journal=Depends(get_trade_journal),
    position_repo: PositionRepository = Depends(get_position_repository),
):
    """Get historical P&L curve.
    
    Returns daily/weekly/monthly P&L for equity curve visualization.
    Uses trade journal closed trades, with PositionManager fallback.
    """
    try:
        from_dt = datetime.fromisoformat(from_date) if from_date else None
        to_dt = datetime.fromisoformat(to_date) if to_date else None

        pnl_data: dict[str, dict] = {}
        source = "journal"

        trades = journal.get_trades(status="CLOSED", limit=10000)
        if trades:
            for trade in trades:
                exit_time = trade.get("exit_time")
                if not exit_time:
                    continue
                ts = datetime.fromisoformat(str(exit_time).replace("Z", "+00:00"))
                if from_dt and ts < from_dt:
                    continue
                if to_dt and ts > to_dt:
                    continue

                if group_by == "day":
                    key = ts.strftime("%Y-%m-%d")
                elif group_by == "week":
                    key = ts.strftime("%Y-W%U")
                elif group_by == "month":
                    key = ts.strftime("%Y-%m")
                else:
                    key = ts.strftime("%Y-%m-%d")

                pnl = float(trade.get("pnl") or 0.0)
                if key not in pnl_data:
                    pnl_data[key] = {"date": key, "pnl": 0.0, "trades": 0}
                pnl_data[key]["pnl"] += pnl
                pnl_data[key]["trades"] += 1
        else:
            source = "positions"
            for position in position_repo.get_positions():
                if position.realized_pnl == 0:
                    continue
                ts = getattr(position, "updated_at", None) or datetime.now()
                if from_dt and ts < from_dt:
                    continue
                if to_dt and ts > to_dt:
                    continue

                if group_by == "day":
                    key = ts.strftime("%Y-%m-%d")
                elif group_by == "week":
                    key = ts.strftime("%Y-W%U")
                elif group_by == "month":
                    key = ts.strftime("%Y-%m")
                else:
                    key = ts.strftime("%Y-%m-%d")

                pnl = float(position.realized_pnl)
                if key not in pnl_data:
                    pnl_data[key] = {"date": key, "pnl": 0.0, "trades": 0}
                pnl_data[key]["pnl"] += pnl
                pnl_data[key]["trades"] += 1

        pnl_curve = sorted(pnl_data.values(), key=lambda x: x["date"])

        return {
            "pnl_curve": pnl_curve,
            "group_by": group_by,
            "total_pnl": sum(p["pnl"] for p in pnl_curve),
            "total_trades": sum(p["trades"] for p in pnl_curve),
            "count": len(pnl_curve),
            "source": source,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("P&L history fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"P&L history fetch failed: {str(exc)}",
        )


@router.post("/square-off", response_model=dict)
async def square_off_positions(
    symbol: Optional[str] = Query(None, description="Square off specific symbol"),
    position_repo: PositionRepository = Depends(get_position_repository),
    order_repo=Depends(get_order_repository),
    broker_service=Depends(get_broker_service),
):
    """Square off all or specific positions.
    
    Closes all open positions or specific symbol position.
    Uses real OMS to place market orders for position closure.
    """
    try:
        positions = position_repo.get_positions()
        
        # Filter positions to square off
        if symbol:
            positions = [p for p in positions if p.symbol.upper() == symbol.upper()]
        else:
            positions = [p for p in positions if p.quantity != 0]
        
        if not positions:
            return {
                "status": "no_positions",
                "message": "No positions to square off",
                "squared_off": 0,
            }

        submit_fn = getattr(broker_service, "submit_order", None) if broker_service else None
        if submit_fn is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Broker order submission unavailable.",
                headers={"Retry-After": "60"},
            )
        
        squared_off = []
        failed = []
        
        for p in positions:
            try:
                # Determine opposite side
                opposite_side = Side.SELL if p.quantity > 0 else Side.BUY
                quantity = abs(p.quantity)
                
                from domain.requests import OrderRequest as DomainOrderRequest
                from brokers.common.oms.order_repository_adapter import request_to_command

                domain_req = DomainOrderRequest(
                    symbol=p.symbol,
                    exchange=p.exchange,
                    transaction_type=opposite_side,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    price=Decimal("0"),
                    product_type=ProductType.INTRADAY,
                    correlation_id=f"square-off-{datetime.now().isoformat()}",
                )

                result = order_repo.place_command(request_to_command(domain_req), submit_fn=submit_fn)
                
                if result.success:
                    squared_off.append({
                        "symbol": p.symbol,
                        "quantity": quantity,
                        "side": opposite_side.value,
                        "order_id": result.order.order_id if result.order else None,
                    })
                else:
                    failed.append({
                        "symbol": p.symbol,
                        "error": result.error or "Unknown error",
                    })
            except Exception as exc:
                failed.append({
                    "symbol": p.symbol,
                    "error": str(exc),
                })
        
        return {
            "status": "completed",
            "squared_off": len(squared_off),
            "failed": len(failed),
            "details": {
                "squared_off": squared_off,
                "failed": failed,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Square-off failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Square-off failed: {str(exc)}",
        )
