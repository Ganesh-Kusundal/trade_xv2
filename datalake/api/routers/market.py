"""Market data endpoints (quotes, candles)."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status

from datalake.api.deps import get_datalake_gateway
from datalake.api.schemas import Candle, CandlesResponse, QuoteResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    symbol: str = Query(..., description="Symbol to fetch"),
    timeframe: str = Query(..., description="Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"),
    from_ts: Optional[int] = Query(None, description="Start timestamp (ms)"),
    to_ts: Optional[int] = Query(None, description="End timestamp (ms)"),
    limit: int = Query(200, ge=1, le=5000, description="Max candles"),
):
    """Get historical OHLCV candles from the data lake.
    
    Supports multiple timeframes and date range filtering.
    Data is sourced from Parquet files in market_data/.
    """
    gateway = get_datalake_gateway()
    
    try:
        # Load data from DataLakeGateway
        df = gateway._load_parquet(symbol, timeframe)
        
        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No candle data found for {symbol}/{timeframe}",
            )
        
        # Ensure timestamp column exists
        if "timestamp" not in df.columns:
            df["timestamp"] = df.index
        
        # Filter by date range if provided
        if from_ts is not None:
            from_dt = pd.Timestamp(from_ts, unit="ms")
            df = df[df["timestamp"] >= from_dt]
        
        if to_ts is not None:
            to_dt = pd.Timestamp(to_ts, unit="ms")
            df = df[df["timestamp"] <= to_dt]
        
        # Sort by timestamp and limit
        df = df.sort_values("timestamp").tail(limit)
        
        # Convert to Candle objects
        candles = []
        for _, row in df.iterrows():
            ts = row["timestamp"]
            if isinstance(ts, pd.Timestamp):
                ts_ms = int(ts.timestamp() * 1000)
            else:
                ts_ms = int(ts)
            
            candles.append(Candle(
                t=ts_ms,
                o=float(row.get("open", 0)),
                h=float(row.get("high", 0)),
                l=float(row.get("low", 0)),
                c=float(row.get("close", 0)),
                v=float(row.get("volume", 0)),
                oi=float(row.get("oi", 0)),
            ))
        
        return CandlesResponse(
            symbol=symbol,
            timeframe=timeframe,
            exchange="NSE",
            candles=candles,
            count=len(candles),
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Candle fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Candle fetch failed: {str(exc)}",
        )


@router.get("/quote/{symbol}", response_model=QuoteResponse)
async def get_quote(symbol: str, exchange: str = Query("NSE", description="Exchange")):
    """Get latest quote/LTP snapshot for a symbol.
    
    Returns the most recent candle's close price as LTP,
    along with OHLCV data from the last available bar.
    """
    gateway = get_datalake_gateway()
    
    try:
        # Get latest 1m candle
        df = gateway._load_parquet(symbol, "1m")
        
        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No quote data found for {symbol}",
            )
        
        # Get latest row
        if "timestamp" not in df.columns:
            df["timestamp"] = df.index
        
        latest = df.sort_values("timestamp").iloc[-1]
        
        ts = latest["timestamp"]
        if isinstance(ts, pd.Timestamp):
            ts_ms = int(ts.timestamp() * 1000)
        else:
            ts_ms = int(ts)
        
        return QuoteResponse(
            symbol=symbol,
            exchange=exchange,
            ltp=float(latest.get("close", 0)),
            timestamp=ts_ms,
            open=float(latest.get("open", 0)),
            high=float(latest.get("high", 0)),
            low=float(latest.get("low", 0)),
            close=float(latest.get("close", 0)),
            volume=float(latest.get("volume", 0)),
            oi=float(latest.get("oi", 0)),
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Quote fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quote fetch failed: {str(exc)}",
        )
