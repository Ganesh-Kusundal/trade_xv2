"""Separate historical endpoints for equities, options, and futures (ADR-0023)."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from domain.candles.contract_historical import ContractHistoricalQuery
from domain.candles.historical import InstrumentRef
from domain.historical.contract_state import ContractState
from domain.instruments.instrument_id import InstrumentId
from interface.api.auth import require_auth
from interface.api.deps import get_datalake_gateway, get_execution_composer
from interface.api.schemas import CandlesResponse
from interface.api.candle_mapper import series_to_api_candles

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/equities/candles", response_model=CandlesResponse)
async def get_equity_candles(
    symbol: str = Query(...),
    exchange: str = Query("NSE"),
    timeframe: str = Query("1d"),
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
):
    """Historical equity candles from datalake (cached)."""
    gateway = get_datalake_gateway()
    df = gateway.query_candles(symbol, timeframe)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    instrument = InstrumentRef(symbol=symbol, exchange=exchange)
    from domain.candles.historical import HistoricalSeries

    series = HistoricalSeries.from_datalake_df(
        df, instrument, timeframe, request_id=f"eq:{symbol}:{timeframe}"
    )
    return CandlesResponse(
        symbol=symbol,
        timeframe=timeframe,
        exchange=exchange,
        candles=series_to_api_candles(series, limit=limit),
        count=min(len(series.bars), limit),
    )


@router.get("/options/candles")
async def get_options_contract_candles(
    instrument_id: str = Query(..., description="Canonical InstrumentId string"),
    timeframe: str = Query("5m"),
    from_date: str = Query(...),
    to_date: str = Query(...),
    contract_state: str = Query("auto"),
    allow_partial: bool = Query(False),
    execution=Depends(get_execution_composer),
):
    """Contract option candles — lake read when present, else live federated fetch."""
    from application.data.contract_historical_coordinator import ContractHistoricalCoordinator

    try:
        iid = InstrumentId.parse(instrument_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    gateway = get_datalake_gateway()
    df = gateway.query_contract_candles(
        iid, timeframe, asset_class="option"
    )
    if df is not None and not df.empty:
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "contract_state": contract_state,
            "rows": len(df),
            "source": "datalake",
            "degraded": False,
        }

    query = ContractHistoricalQuery(
        instrument=iid,
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        timeframe=timeframe,
        contract_state=ContractState(contract_state),
        allow_partial=allow_partial,
    )
    coordinator = ContractHistoricalCoordinator(
        execution._registry,
        execution._router,
        lambda bid, ep, pri: execution._quota_scheduler.acquire(bid, ep, pri),
    )
    df, ledger = coordinator.fetch(query)
    return {
        "instrument_id": instrument_id,
        "timeframe": timeframe,
        "contract_state": contract_state,
        "rows": len(df),
        "source": "live",
        "provenance": ledger.to_summary_dict(),
        "degraded": ledger.degraded,
    }


@router.get("/futures/candles")
async def get_futures_contract_candles(
    instrument_id: str = Query(...),
    timeframe: str = Query("5m"),
    from_date: str = Query(...),
    to_date: str = Query(...),
    contract_state: str = Query("auto"),
    expired_instrument_key: str | None = Query(None),
    allow_partial: bool = Query(False),
    execution=Depends(get_execution_composer),
):
    """Contract future candles — lake read when present, else live federated fetch."""
    from application.data.contract_historical_coordinator import ContractHistoricalCoordinator

    try:
        iid = InstrumentId.parse(instrument_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    gateway = get_datalake_gateway()
    df = gateway.query_contract_candles(
        iid, timeframe, asset_class="future"
    )
    if df is not None and not df.empty:
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "contract_state": contract_state,
            "rows": len(df),
            "source": "datalake",
            "degraded": False,
        }

    query = ContractHistoricalQuery(
        instrument=iid,
        from_date=date.fromisoformat(from_date),
        to_date=date.fromisoformat(to_date),
        timeframe=timeframe,
        contract_state=ContractState(contract_state),
        expired_instrument_key=expired_instrument_key,
        allow_partial=allow_partial,
    )
    coordinator = ContractHistoricalCoordinator(
        execution._registry,
        execution._router,
        lambda bid, ep, pri: execution._quota_scheduler.acquire(bid, ep, pri),
    )
    df, ledger = coordinator.fetch(query)
    return {
        "instrument_id": instrument_id,
        "timeframe": timeframe,
        "contract_state": contract_state,
        "rows": len(df),
        "source": "live",
        "provenance": ledger.to_summary_dict(),
        "degraded": ledger.degraded,
    }
