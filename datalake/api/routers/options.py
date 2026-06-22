"""Options endpoints (chain, Greeks, PCR, max pain)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from datalake.api.deps import get_view_manager
from datalake.api.schemas import (
    OptionChainResponse,
    OptionContract,
    PCRResponse,
    MaxPainResponse,
    IVSurfaceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/chain/{underlying}", response_model=OptionChainResponse)
async def get_option_chain(
    underlying: str,
    expiry: Optional[str] = Query(None, description="Expiry date (YYYY-MM-DD)"),
    strike_range: int = Query(10, ge=1, le=50, description="Number of strikes from ATM"),
):
    """Get option chain for an underlying.
    
    Returns CE/PE contracts with Greeks, OI, volume, and LTP.
    Reads directly from option parquet files.
    """
    import duckdb
    
    try:
        options_dir = Path("market_data/options/candles")
        underlying_dir = options_dir / f"underlying={underlying.upper()}"
        
        if not underlying_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No option data found for {underlying}",
            )
        
        parquet_pattern = str(underlying_dir / "**" / "data.parquet")
        
        query = f"""
            SELECT symbol, expiry_date, strike, option_type,
                   close as ltp, volume, oi
            FROM read_parquet('{parquet_pattern}', hive_partitioning=true)
            WHERE underlying = ?
        """
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry_date = ?"
            params.append(expiry)
        
        query += f" ORDER BY strike, option_type LIMIT {int(strike_range * 2)}"
        
        conn = duckdb.connect(":memory:")
        results = conn.execute(query, params).fetchall()
        conn.close()
        
        contracts = []
        for row in results:
            contracts.append(OptionContract(
                symbol=row[0],
                expiry=str(row[1]) if row[1] else "",
                strike=float(row[2]) if row[2] else 0.0,
                option_type=row[3] or "CE",
                ltp=float(row[4]) if row[4] else 0.0,
                bid=0.0,  # Not available from OHLCV parquet
                ask=0.0,  # Not available from OHLCV parquet
                volume=float(row[5]) if row[5] else 0.0,
                oi=float(row[6]) if row[6] else 0.0,
            ))
        
        return OptionChainResponse(
            underlying=underlying,
            expiry=expiry or "all",
            contracts=contracts,
            count=len(contracts),
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Option chain fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Option chain fetch failed: {str(exc)}",
        )


@router.get("/pcr/{underlying}", response_model=PCRResponse)
async def get_pcr(
    underlying: str,
    expiry: Optional[str] = Query(None, description="Expiry date"),
):
    """Get Put-Call Ratio (OI and Volume based).
    
    Queries v_pcr view for PCR metrics.
    """
    vm = get_view_manager()
    
    try:
        query = """
            SELECT timestamp, underlying, expiry_kind, expiry_date, spot,
                   pcr_volume, pcr_oi, total_ce_volume, total_pe_volume,
                   total_ce_oi, total_pe_oi
            FROM v_pcr WHERE underlying = ?
        """
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry_date = ?"
            params.append(expiry)
        
        query += " ORDER BY timestamp DESC LIMIT 1"
        
        result = vm.query(query, params).fetchone()
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No PCR data found for {underlying}",
            )
        
        ts = result[0]
        ts_ms = int(ts.timestamp() * 1000) if hasattr(ts, 'timestamp') else int(ts)
        
        return PCRResponse(
            timestamp=ts_ms,
            underlying=result[1] or underlying,
            expiry_kind=result[2] or "MONTH",
            expiry_date=str(result[3]) if result[3] else "",
            spot=float(result[4]) if result[4] else 0.0,
            pcr_volume=float(result[5]) if result[5] else None,
            pcr_oi=float(result[6]) if result[6] else None,
            total_ce_volume=float(result[7]) if result[7] else 0.0,
            total_pe_volume=float(result[8]) if result[8] else 0.0,
            total_ce_oi=float(result[9]) if result[9] else 0.0,
            total_pe_oi=float(result[10]) if result[10] else 0.0,
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PCR fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PCR fetch failed: {str(exc)}",
        )


@router.get("/max-pain/{underlying}", response_model=MaxPainResponse)
async def get_max_pain(
    underlying: str,
    expiry: Optional[str] = Query(None, description="Expiry date"),
):
    """Get max pain level for an underlying.
    
    Queries v_max_pain view for strike with maximum option writer profit.
    """
    vm = get_view_manager()
    
    try:
        query = """
            SELECT timestamp, underlying, expiry_kind, expiry_date, spot,
                   max_pain_strike, total_pain_at_max_pain, distance_from_spot,
                   position_vs_spot
            FROM v_max_pain WHERE underlying = ?
        """
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry_date = ?"
            params.append(expiry)
        
        query += " ORDER BY timestamp DESC LIMIT 1"
        
        result = vm.query(query, params).fetchone()
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No max pain data found for {underlying}",
            )
        
        ts = result[0]
        ts_ms = int(ts.timestamp() * 1000) if hasattr(ts, 'timestamp') else int(ts)
        
        return MaxPainResponse(
            timestamp=ts_ms,
            underlying=result[1] or underlying,
            expiry_kind=result[2] or "MONTH",
            expiry_date=str(result[3]) if result[3] else "",
            spot=float(result[4]) if result[4] else 0.0,
            max_pain_strike=float(result[5]) if result[5] else 0.0,
            total_pain_at_max_pain=float(result[6]) if result[6] else 0.0,
            distance_from_spot=float(result[7]) if result[7] else 0.0,
            position_vs_spot=result[8] or "at_spot",
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Max pain fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Max pain fetch failed: {str(exc)}",
        )


@router.get("/iv-surface/{underlying}", response_model=IVSurfaceResponse)
async def get_iv_surface(
    underlying: str,
    expiry: Optional[str] = Query(None, description="Expiry date"),
    option_type: Optional[str] = Query(None, description="CE, PE, or both"),
):
    """Get IV surface for 3D visualization.
    
    Returns IV by strike and expiry for surface plot.
    """
    vm = get_view_manager()
    
    try:
        query = """
            SELECT timestamp, underlying, expiry_kind, expiry_date, spot,
                   atm_strike, atm_iv, otm_put_iv, otm_call_iv, iv_skew,
                   put_call_iv_ratio, days_to_expiry
            FROM v_iv_surface
            WHERE underlying = ?
        """
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry_date = ?"
            params.append(expiry)
        
        query += " ORDER BY timestamp DESC LIMIT 1"
        
        result = vm.query(query, params).fetchone()
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No IV surface data found for {underlying}",
            )
        
        ts = result[0]
        ts_ms = int(ts.timestamp() * 1000) if hasattr(ts, 'timestamp') else int(ts)
        
        return IVSurfaceResponse(
            timestamp=ts_ms,
            underlying=result[1] or underlying,
            expiry_kind=result[2] or "MONTH",
            expiry_date=str(result[3]) if result[3] else "",
            spot=float(result[4]) if result[4] else 0.0,
            atm_strike=float(result[5]) if result[5] else 0.0,
            atm_iv=float(result[6]) if result[6] else 0.0,
            otm_put_iv=float(result[7]) if result[7] else 0.0,
            otm_call_iv=float(result[8]) if result[8] else 0.0,
            iv_skew=float(result[9]) if result[9] else 0.0,
            put_call_iv_ratio=float(result[10]) if result[10] else None,
            days_to_expiry=int(result[11]) if result[11] else 0,
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("IV surface fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"IV surface fetch failed: {str(exc)}",
        )


@router.get("/volume-profile/{underlying}", response_model=dict)
async def get_options_volume_profile(
    underlying: str,
    expiry: Optional[str] = Query(None, description="Expiry date"),
):
    """Get options volume profile by strike."""
    # TODO: Implement with volume profile analytics
    return {"strikes": [], "profile": []}
