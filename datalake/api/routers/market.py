"""Market data endpoints (quotes, candles)."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status

from datalake.api.deps import get_datalake_gateway
from datalake.api.auth import require_auth
from datalake.api.freshness import check_data_freshness
from fastapi import Depends, Response
from datalake.api.schemas import Candle, CandlesResponse, QuoteResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


# Cache TTL configuration by timeframe category
# Intraday (1m-5m): 30 seconds - changes frequently
# Intraday (15m-4h): 300 seconds (5 min) - moderate changes
# Daily/Weekly: 3600 seconds (1 hour) - changes once per day
CACHE_TTL_CONFIG = {
    "1m": 30,
    "3m": 30,
    "5m": 30,
    "15m": 300,
    "30m": 300,
    "1h": 300,
    "4h": 300,
    "1d": 3600,
    "1w": 3600,
}

QUOTE_CACHE_TTL = 10  # Quote changes very frequently


def get_cache_ttl_for_timeframe(timeframe: str) -> int:
    """Get cache TTL in seconds based on timeframe.
    
    Intraday timeframes have shorter TTLs as data changes more frequently.
    """
    return CACHE_TTL_CONFIG.get(timeframe, 300)  # Default to 5 minutes


def build_cache_control_header(max_age: int, stale_while_revalidate: Optional[int] = None) -> str:
    """Build Cache-Control header value following HTTP spec.
    
    Args:
        max_age: Max age in seconds
        stale_while_revalidate: Optional SWR duration
        
    Returns:
        Cache-Control header value
    """
    directives = [f"public", f"max-age={max_age}"]
    if stale_while_revalidate:
        directives.append(f"stale-while-revalidate={stale_while_revalidate}")
    return ", ".join(directives)


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    symbol: str = Query(..., description="Symbol to fetch"),
    timeframe: str = Query(..., description="Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"),
    from_ts: Optional[int] = Query(None, description="Start timestamp (ms)"),
    to_ts: Optional[int] = Query(None, description="End timestamp (ms)"),
    limit: int = Query(200, ge=1, le=5000, description="Max candles"),
    response: Response = None,
):
    """Get historical OHLCV candles from the data lake.
    
    Supports multiple timeframes and date range filtering.
    Data is sourced from Parquet files in market_data/.
    
    Cache-Control headers vary by timeframe:
    - 1m-5m: max-age=30 (30 seconds)
    - 15m-4h: max-age=300 (5 minutes)
    - 1d-1w: max-age=3600 (1 hour)
    
    Freshness headers:
    - X-Data-Stale: true/false
    - X-Data-Last-Update: date of most recent candle
    - X-Data-Days-Old: age in days
    - X-Data-Freshness: ISO timestamp of most recent candle
    - X-Data-Type: historical
    """
    from fastapi.responses import JSONResponse
    
    gateway = get_datalake_gateway()
    
    try:
        # Load data from DataLakeGateway
        df = gateway._load_parquet(symbol, timeframe)
        
        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No candle data found for {symbol}/{timeframe}",
            )
        
        # Check data freshness
        freshness = check_data_freshness(df, timeframe)
        if response:
            response.headers["X-Data-Stale"] = str(freshness.is_stale).lower()
            if freshness.last_update:
                response.headers["X-Data-Last-Update"] = freshness.last_update.isoformat()
            response.headers["X-Data-Days-Old"] = str(freshness.days_old)
        
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
        
        # Vectorized conversion — use df.to_dict('records') to avoid iterrows overhead
        # P0.8: Replaced df.iterrows() with vectorized list comprehension
        rows = df.to_dict(orient="records")
        ts_col = df["timestamp"]
        if len(ts_col) > 0 and isinstance(ts_col.iloc[0], pd.Timestamp):
            # Convert to milliseconds: pandas 3.0 uses datetime64[us], so cast to datetime64[ms] first
            ts_ms = ts_col.astype("datetime64[ms]").astype("int64").tolist()
        else:
            ts_ms = ts_col.astype("int64").tolist()
        
        candles = [
            Candle(
                t=ts_ms[i],
                o=float(r["open"]) if pd.notna(r.get("open")) else 0.0,
                h=float(r["high"]) if pd.notna(r.get("high")) else 0.0,
                l=float(r["low"]) if pd.notna(r.get("low")) else 0.0,
                c=float(r["close"]) if pd.notna(r.get("close")) else 0.0,
                v=float(r["volume"]) if pd.notna(r.get("volume")) else 0.0,
                oi=float(r.get("oi", 0)) if pd.notna(r.get("oi", 0)) else 0.0,
            )
            for i, r in enumerate(rows)
        ]
        
        # Get most recent candle timestamp for X-Data-Freshness header
        latest_timestamp = None
        if candles:
            latest_ts_ms = candles[-1].t
            latest_timestamp = pd.Timestamp(latest_ts_ms, unit="ms").isoformat()
        
        response = JSONResponse(content={
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": "NSE",
            "candles": [c.model_dump() for c in candles],
            "count": len(candles),
        })
        
        # P0.7: Add Cache-Control headers with timeframe-aware TTL
        max_age = get_cache_ttl_for_timeframe(timeframe)
        stale_while_revalidate = max_age * 4  # SWR = 4x max-age
        response.headers["Cache-Control"] = build_cache_control_header(
            max_age=max_age,
            stale_while_revalidate=stale_while_revalidate
        )
        response.headers["X-Cache-TTL"] = str(max_age)
        response.headers["X-Data-Type"] = "historical"
        
        # Add freshness timestamp
        if latest_timestamp:
            response.headers["X-Data-Freshness"] = latest_timestamp
        
        return response
        
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
    
    Cache-Control: max-age=10 (10 seconds) - quotes change frequently.
    """
    from fastapi.responses import JSONResponse
    
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
        
        # Use close price as LTP; handle NaN gracefully
        ltp_value = latest.get("close")
        if pd.isna(ltp_value):
            ltp_value = 0.0
        
        response_data = {
            "symbol": symbol,
            "exchange": exchange,
            "ltp": float(ltp_value),
            "timestamp": ts_ms,
            "open": float(latest.get("open", 0)) if pd.notna(latest.get("open")) else None,
            "high": float(latest.get("high", 0)) if pd.notna(latest.get("high")) else None,
            "low": float(latest.get("low", 0)) if pd.notna(latest.get("low")) else None,
            "close": float(latest.get("close", 0)) if pd.notna(latest.get("close")) else None,
            "volume": float(latest.get("volume", 0)) if pd.notna(latest.get("volume")) else None,
            "oi": float(latest.get("oi", 0)) if pd.notna(latest.get("oi")) else None,
        }
        
        response = JSONResponse(content=response_data)
        
        # P0.7: Add Cache-Control headers for quote endpoint
        max_age = QUOTE_CACHE_TTL
        stale_while_revalidate = max_age * 6  # SWR = 60 seconds
        response.headers["Cache-Control"] = build_cache_control_header(
            max_age=max_age,
            stale_while_revalidate=stale_while_revalidate
        )
        response.headers["X-Cache-TTL"] = str(max_age)
        response.headers["X-Data-Type"] = "quote"
        
        # Add freshness timestamp
        freshness_ts = pd.Timestamp(ts_ms, unit="ms").isoformat()
        response.headers["X-Data-Freshness"] = freshness_ts
        
        return response
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Quote fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quote fetch failed: {str(exc)}",
        )
