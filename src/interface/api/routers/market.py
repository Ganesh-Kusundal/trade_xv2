"""Market data endpoints (quotes, candles).

Provides:
- /candles — Historical OHLCV from datalake (cached parquet files)
- /quote/{symbol} — Latest quote from datalake (cached)
- /live/candles — Historical OHLCV from live brokers via MarketDataComposer
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from domain.candles.historical import HistoricalSeries, InstrumentRef
from domain.constants.market import IST
from domain.instruments.timeframes import normalize_timeframe
from interface.api.auth import require_auth
from interface.api.candle_mapper import series_to_api_candles
from interface.api.deps import get_datalake_gateway, get_market_data_composer
from interface.api.freshness import check_data_freshness
from interface.api.schemas import CandlesResponse, QuoteResponse
from interface.api.session_state import get_session, set_session

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


def build_cache_control_header(max_age: int, stale_while_revalidate: int | None = None) -> str:
    """Build Cache-Control header value following HTTP spec.

    Args:
        max_age: Max age in seconds
        stale_while_revalidate: Optional SWR duration

    Returns:
        Cache-Control header value
    """
    directives = ["public", f"max-age={max_age}"]
    if stale_while_revalidate:
        directives.append(f"stale-while-revalidate={stale_while_revalidate}")
    return ", ".join(directives)


@router.get("/candles", response_model=CandlesResponse)
async def get_candles(
    symbol: str = Query(..., description="Symbol to fetch"),
    exchange: str = Query("NSE", description="Exchange (NSE, BSE, NFO, etc.)"),
    timeframe: str = Query(..., description="Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"),
    from_ts: int | None = Query(None, description="Start timestamp (ms)"),
    to_ts: int | None = Query(None, description="End timestamp (ms)"),
    limit: int = Query(200, ge=1, le=5000, description="Max candles"),
):
    """Get historical OHLCV candles from the data lake.

    Supports multiple timeframes and date range filtering.
    Data is sourced from Parquet files in data/lake/.

    Cache-Control headers vary by timeframe:
    - 1m-5m: max-age=30 (30 seconds)
    - 15m-4h: max-age=300 (5 minutes)
    - 1d-1w: max-age=3600 (1 hour)

    Freshness headers:
    - X-Data-Stale: true/false
    - X-Data-Last-Update: date of most recent candle
    - X-Data-Days-Old: age in days
    - X-Data-Freshness: ISO timestamp of most recent candle (IST, +05:30)
    - X-Data-Type: historical
    """
    from fastapi.responses import JSONResponse

    gateway = get_datalake_gateway()

    try:
        # Build timestamp filters
        from_ts_pd = pd.Timestamp(from_ts, unit="ms") if from_ts is not None else None
        to_ts_pd = pd.Timestamp(to_ts, unit="ms") if to_ts is not None else None

        # Use DuckDB predicate pushdown instead of loading entire parquet
        df = gateway.query_candles(
            symbol,
            timeframe,
            from_ts=from_ts_pd,
            to_ts=to_ts_pd,
            limit=limit,
        )

        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No candle data found for {symbol}/{timeframe}",
            )

        freshness = check_data_freshness(df, timeframe)

        instrument = InstrumentRef(symbol=symbol, exchange=exchange)
        series = HistoricalSeries.from_datalake_df(
            df,
            instrument,
            normalize_timeframe(timeframe),
            request_id=f"lake:{symbol}:{timeframe}",
        )
        candles = series_to_api_candles(series, limit=limit)

        latest_timestamp = None
        if not df.empty:
            latest_lake_ts = pd.to_datetime(df["timestamp"]).max()
            latest_timestamp = latest_lake_ts.tz_localize(IST).isoformat()

        response = JSONResponse(
            content={
                "symbol": symbol,
                "timeframe": timeframe,
                "exchange": exchange,
                "candles": [c.model_dump() for c in candles],
                "count": len(candles),
            }
        )

        response.headers["X-Data-Stale"] = str(freshness.is_stale).lower()
        if freshness.last_update:
            response.headers["X-Data-Last-Update"] = freshness.last_update.isoformat()
        response.headers["X-Data-Days-Old"] = str(freshness.days_old)

        # P0.7: Add Cache-Control headers with timeframe-aware TTL
        max_age = get_cache_ttl_for_timeframe(timeframe)
        stale_while_revalidate = max_age * 4  # SWR = 4x max-age
        response.headers["Cache-Control"] = build_cache_control_header(
            max_age=max_age, stale_while_revalidate=stale_while_revalidate
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
            detail=f"Candle fetch failed: {exc!s}",
        ) from exc


@router.get("/live/candles", response_model=CandlesResponse)
async def get_live_candles(
    symbol: str = Query(..., description="Symbol to fetch"),
    exchange: str = Query("NSE", description="Exchange (NSE, BSE, NFO, etc.)"),
    timeframe: str = Query(..., description="Timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"),
    from_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    limit: int = Query(200, ge=1, le=5000, description="Max candles"),
    composer=Depends(get_market_data_composer),
):
    """Get historical OHLCV candles from live brokers via multi-broker architecture.

    Uses MarketDataComposer to:
    - Route to optimal broker based on policy
    - Fetch with quota management
    - Merge data from multiple brokers if needed
    - Include full provenance audit trail

    This endpoint fetches REAL-TIME data from brokers (not cached).
    Use /candles for cached datalake data.
    """
    from fastapi.responses import JSONResponse

    try:
        from application.data.historical_coordinator import HistoricalQuery

        query = HistoricalQuery(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=timeframe,
            from_date=date.fromisoformat(from_date),
            to_date=date.fromisoformat(to_date),
        )

        series, ledger = await composer.fetch_historical(query)

        if series.bar_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No candle data found for {symbol}/{timeframe}",
            )

        if series.is_degraded:
            logger.warning("Live candle data degraded: %s", ledger.issues)

        # Convert to candles
        candles = series_to_api_candles(series, limit=limit)

        response = JSONResponse(
            content={
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe,
                "candles": [c.model_dump() for c in candles],
                "count": len(candles),
                "provenance": {
                    "request_id": ledger.request_id,
                    "degraded": ledger.degraded,
                    "issues": ledger.issues,
                    "sources": [
                        {
                            "broker_id": src.broker_id,
                            "bar_count": src.bar_count,
                            "is_primary": src.is_primary,
                        }
                        for src in ledger.sources
                    ],
                },
            }
        )

        response.headers["X-Data-Type"] = "live-broker"
        response.headers["X-Request-ID"] = ledger.request_id
        if ledger.degraded:
            response.headers["X-Data-Degraded"] = "true"

        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Live candle fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Live candle fetch failed: {exc!s}",
        ) from exc


@router.get("/quote/{symbol}", response_model=QuoteResponse)
async def get_quote(symbol: str, exchange: str = Query("NSE", description="Exchange")):
    """Get latest quote/LTP snapshot for a symbol via domain objects.

    Cache-Control: max-age=10 (10 seconds) - quotes change frequently.
    """
    from fastapi.responses import JSONResponse

    session = get_session()
    instrument = session.universe.equity(symbol, exchange)

    try:
        q = instrument.refresh()

        if q is None or (q.ltp == 0 and q.open == 0 and q.volume == 0):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No quote data found for {symbol}",
            )

        ts_ms = int(q.event_time.timestamp() * 1000) if q.event_time else 0

        response_data = {
            "symbol": symbol,
            "exchange": exchange,
            "ltp": float(q.ltp),
            "timestamp": ts_ms,
            "open": float(q.open) if q.open else None,
            "high": float(q.high) if q.high else None,
            "low": float(q.low) if q.low else None,
            "close": float(q.close) if q.close else None,
            "volume": float(q.volume) if q.volume else 0.0,
            "oi": 0.0,
        }

        response = JSONResponse(content=response_data)

        max_age = QUOTE_CACHE_TTL
        stale_while_revalidate = max_age * 6
        response.headers["Cache-Control"] = build_cache_control_header(
            max_age=max_age, stale_while_revalidate=stale_while_revalidate
        )
        response.headers["X-Cache-TTL"] = str(max_age)
        response.headers["X-Data-Type"] = "quote"

        freshness_ts = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert(IST).isoformat()
        response.headers["X-Data-Freshness"] = freshness_ts

        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Quote fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quote fetch failed: {exc!s}",
        ) from exc
