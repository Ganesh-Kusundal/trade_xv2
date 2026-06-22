"""Scanner endpoints (results, candidates, run scans)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from datalake.api.deps import get_view_manager
from datalake.api.schemas import ScannerCandidatesResponse, ScannerSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/results", response_model=dict)
async def get_scan_results(
    scanner_name: Optional[str] = Query(None, description="Filter by scanner name"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
):
    """Get historical scanner results from scan store.
    
    Returns completed scan results with candidates and metrics.
    """
    # TODO: Implement with scan_store.get_recent_scans()
    return {"scans": [], "count": 0}


@router.get("/top-candidates", response_model=ScannerCandidatesResponse)
async def get_top_candidates(
    limit: int = Query(10, ge=1, le=50, description="Max candidates"),
):
    """Get top scanner candidates.
    
    Delegates to analytics endpoint for v_top3/v_top10.
    """
    vm = get_view_manager()
    
    try:
        view_name = "v_top3_candidates" if limit <= 3 else "v_top10_candidates"
        
        query = f"""
            SELECT symbol, ltp, intraday_score, signal, trend,
                   rsi_14, roc_5, relative_volume, day_high, day_low, day_volume
            FROM {view_name}
            LIMIT ?
        """
        
        results = vm.query(query, [limit]).fetchall()
        
        candidates = []
        for row in results:
            candidates.append(ScannerSnapshot(
                symbol=row[0],
                ltp=float(row[1]) if row[1] else 0.0,
                intraday_score=float(row[2]) if row[2] else 0.0,
                signal=row[3] or "NEUTRAL",
                trend=row[4] or "Neutral",
                rsi_14=float(row[5]) if row[5] else None,
                roc_5=float(row[6]) if row[6] else None,
                relative_volume=float(row[7]) if row[7] else None,
                day_high=float(row[8]) if row[8] else None,
                day_low=float(row[9]) if row[9] else None,
                day_volume=float(row[10]) if row[10] else None,
            ))
        
        return ScannerCandidatesResponse(
            candidates=candidates,
            count=len(candidates),
        )
        
    except Exception as exc:
        logger.error("Top candidates fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Top candidates fetch failed: {str(exc)}",
        )


@router.get("/snapshots", response_model=ScannerCandidatesResponse)
async def get_snapshots(
    limit: int = Query(50, ge=1, le=500, description="Max symbols"),
):
    """Get full intraday scanner snapshots.
    
    Returns v_intraday_snapshot for all active symbols.
    """
    vm = get_view_manager()
    
    try:
        query = """
            SELECT symbol, ltp, intraday_score, signal, trend,
                   rsi_approx, roc_5, relative_volume, day_high, day_low, day_volume
            FROM v_intraday_snapshot
            ORDER BY intraday_score DESC
            LIMIT ?
        """
        
        results = vm.query(query, [limit]).fetchall()
        
        candidates = []
        for row in results:
            candidates.append(ScannerSnapshot(
                symbol=row[0],
                ltp=float(row[1]) if row[1] else 0.0,
                intraday_score=float(row[2]) if row[2] else 0.0,
                signal=row[3] or "NEUTRAL",
                trend=row[4] or "Neutral",
                rsi_14=float(row[5]) if row[5] else None,
                roc_5=float(row[6]) if row[6] else None,
                relative_volume=float(row[7]) if row[7] else None,
                day_high=float(row[8]) if row[8] else None,
                day_low=float(row[9]) if row[9] else None,
                day_volume=float(row[10]) if row[10] else None,
            ))
        
        return ScannerCandidatesResponse(
            candidates=candidates,
            count=len(candidates),
        )
        
    except Exception as exc:
        logger.error("Snapshot fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot fetch failed: {str(exc)}",
        )


@router.post("/run", response_model=dict)
async def run_scan(
    scanner_name: str = Query(..., description="Scanner to run"),
    universe: str = Query("NIFTY500", description="Universe to scan"),
):
    """Trigger a new scanner run.
    
    Executes ScannerRunner.run_all() for the specified scanner
    and universe. Returns scan ID for result retrieval.
    """
    # TODO: Implement with ScannerRunner
    return {
        "scan_id": "scan_001",
        "status": "queued",
        "scanner": scanner_name,
        "universe": universe,
        "timestamp": datetime.now().isoformat(),
    }
