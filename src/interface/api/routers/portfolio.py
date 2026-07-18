"""Portfolio endpoints (positions, holdings, P&L)."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.auth import require_auth
from interface.api.deps import (
    get_event_bus,
    get_order_manager,
    get_position_manager,
    get_position_repository,
    get_risk_manager,
    get_trade_journal,
)
from interface.api.schemas import (
    Holding,
    HoldingsResponse,
    PortfolioSummary,
    Position,
    PositionsResponse,
)
from application.portfolio.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    status_filter: str | None = Query(
        None, alias="status", description="Filter: open, closed, all"
    ),
):
    """Get current positions from OMS.

    Returns open and closed positions from broker or paper trading.
    """
    position_manager = get_position_manager()
    svc = PortfolioService(position_manager=position_manager)
    summary = svc.get_positions(status_filter=status_filter)

    return PositionsResponse(
        positions=[
            Position(
                symbol=p.symbol,
                exchange=p.exchange,
                quantity=p.quantity,
                average_price=p.average_price,
                current_price=p.current_price,
                unrealized_pnl=p.unrealized_pnl,
                realized_pnl=p.realized_pnl,
                pnl_pct=p.pnl_pct,
            )
            for p in summary.positions
        ],
        count=summary.count,
        total_pnl=summary.total_pnl,
        total_pnl_percent=summary.total_pnl_percent,
    )


@router.get("/holdings", response_model=HoldingsResponse)
async def get_holdings():
    """Get current holdings/portfolio.

    Returns long-term holdings with cost basis and current value.
    Uses real PositionManager data, filtering for delivery positions.
    """
    try:
        position_manager = get_position_manager()
        svc = PortfolioService(position_manager=position_manager)
        summary = svc.get_holdings()

        return HoldingsResponse(
            holdings=[
                Holding(
                    symbol=h.symbol,
                    exchange=h.exchange,
                    quantity=h.quantity,
                    average_price=h.average_price,
                    current_price=h.current_price,
                    invested_value=h.invested_value,
                    current_value=h.current_value,
                    pnl=h.pnl,
                    pnl_percent=h.pnl_percent,
                )
                for h in summary.holdings
            ],
            count=summary.count,
            total_value=summary.total_value,
            total_invested=summary.total_invested,
            total_pnl=summary.total_pnl,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Holdings fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Holdings fetch failed: {exc!s}",
        ) from exc


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    position_repo = Depends(get_position_repository),
    risk_manager=Depends(get_risk_manager),
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
                current_price = float(getattr(p, "ltp", Decimal("0")))
                avg_price = float(p.avg_price)
                quantity = abs(p.quantity)

                invested = quantity * avg_price
                current = quantity * current_price

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
                capital = (
                    float(risk_manager.capital_fn()) if hasattr(risk_manager, "capital_fn") else 0.0
                )
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
            detail=f"Portfolio summary fetch failed: {exc!s}",
        ) from exc


@router.get("/pnl", response_model=dict)
async def get_pnl_history(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    group_by: str = Query("day", description="Group by: day, week, month"),
    journal=Depends(get_trade_journal),
    position_repo = Depends(get_position_repository),
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
            detail=f"P&L history fetch failed: {exc!s}",
        ) from exc


@router.post("/square-off", response_model=dict)
async def square_off_positions(
    symbol: str | None = Query(None, description="Square off specific symbol"),
):
    """Square off all or specific positions.

    Closes all open positions or specific symbol position.
    Routes through OMS for risk checks and event publishing.
    """
    from application.oms.square_off_service import SquareOffRejectedError, SquareOffService

    try:
        order_manager = get_order_manager()
        position_manager = get_position_manager()
        risk_manager = get_risk_manager()
        event_bus = get_event_bus()

        svc = SquareOffService(
            order_manager=order_manager,
            position_manager=position_manager,
            risk_manager=risk_manager,
            event_bus=event_bus,
        )

        summary = svc.square_off(symbol=symbol)

        return {
            "status": summary.status,
            "squared_off": summary.squared_off,
            "failed": summary.failed,
            "details": {
                "squared_off": [
                    {"symbol": r.symbol, "quantity": r.quantity, "side": r.side, "order_id": r.order_id}
                    for r in summary.details if r.success
                ],
                "failed": [
                    {"symbol": r.symbol, "error": r.error}
                    for r in summary.details if not r.success
                ],
            },
        }
    except SquareOffRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Square-off failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Square-off failed: {exc!s}",
        ) from exc
