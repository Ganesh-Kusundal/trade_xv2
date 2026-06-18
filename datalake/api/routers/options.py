"""Options endpoints (chain, Greeks, PCR, max pain)."""

from __future__ import annotations

import logging
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
    """
    vm = get_view_manager()
    
    try:
        query = """
            SELECT symbol, expiry, strike, option_type,
                   ltp, bid, ask, volume, oi, iv, delta, gamma, theta, vega
            FROM v_option_chain
            WHERE underlying = ?
        """
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry = ?"
            params.append(expiry)
        
        query += f" ORDER BY strike LIMIT {int(strike_range * 2)}"
        
        results = vm.query(query, params).fetchall()
        
        contracts = []
        for row in results:
            contracts.append(OptionContract(
                symbol=row[0],
                expiry=str(row[1]) if row[1] else "",
                strike=float(row[2]) if row[2] else 0.0,
                option_type=row[3] or "CE",
                ltp=float(row[4]) if row[4] else 0.0,
                bid=float(row[5]) if row[5] else 0.0,
                ask=float(row[6]) if row[6] else 0.0,
                volume=float(row[7]) if row[7] else 0.0,
                oi=float(row[8]) if row[8] else 0.0,
                iv=float(row[9]) if row[9] else None,
                delta=float(row[10]) if row[10] else None,
                gamma=float(row[11]) if row[11] else None,
                theta=float(row[12]) if row[12] else None,
                vega=float(row[13]) if row[13] else None,
            ))
        
        return OptionChainResponse(
            underlying=underlying,
            expiry=expiry or "all",
            contracts=contracts,
            count=len(contracts),
        )
        
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
        query = "SELECT * FROM v_pcr WHERE underlying = ?"
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry = ?"
            params.append(expiry)
        
        result = vm.query(query, params).fetchone()
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No PCR data found for {underlying}",
            )
        
        return PCRResponse(
            underlying=underlying,
            expiry=str(result[1]) if len(result) > 1 else None,
            pcr_oi=float(result[2]) if len(result) > 2 else 0.0,
            pcr_volume=float(result[3]) if len(result) > 3 else 0.0,
            total_ce_oi=float(result[4]) if len(result) > 4 else 0.0,
            total_pe_oi=float(result[5]) if len(result) > 5 else 0.0,
            total_ce_volume=float(result[6]) if len(result) > 6 else 0.0,
            total_pe_volume=float(result[7]) if len(result) > 7 else 0.0,
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
        query = "SELECT * FROM v_max_pain WHERE underlying = ?"
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry = ?"
            params.append(expiry)
        
        result = vm.query(query, params).fetchone()
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No max pain data found for {underlying}",
            )
        
        return MaxPainResponse(
            underlying=underlying,
            expiry=str(result[1]) if len(result) > 1 else None,
            max_pain_strike=float(result[2]) if len(result) > 2 else 0.0,
            total_pain=float(result[3]) if len(result) > 3 else 0.0,
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
            SELECT strike, expiry, iv, option_type
            FROM v_iv_surface
            WHERE underlying = ?
        """
        params = [underlying.upper()]
        
        if expiry:
            query += " AND expiry = ?"
            params.append(expiry)
        
        if option_type:
            query += " AND option_type = ?"
            params.append(option_type.upper())
        
        query += " ORDER BY expiry, strike"
        
        results = vm.query(query, params).fetchall()
        
        surface_points = []
        for row in results:
            surface_points.append({
                "strike": float(row[0]) if row[0] else 0.0,
                "expiry": str(row[1]) if row[1] else "",
                "iv": float(row[2]) if row[2] else 0.0,
                "option_type": row[3] or "CE",
            })
        
        return IVSurfaceResponse(
            underlying=underlying,
            data=surface_points,
            count=len(surface_points),
        )
        
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
"""Options endpoints."""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()

# TODO: Implement options endpoints
