"""Scanner endpoints (results, candidates, run scans)."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from datalake.research.scan_store import get_recent_scans, save_scan_result
from interface.api.auth import require_auth
from interface.api.deps import (
    get_data_catalog,
    get_datalake_gateway,
    get_trading_context,
    get_view_manager,
)
from interface.api.schemas import ScannerCandidatesResponse, ScannerSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/results", response_model=dict)
async def get_scan_results(
    scanner_name: str | None = Query(None, description="Filter by scanner name"),
    date: str | None = Query(None, description="Date in YYYY-MM-DD format"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
):
    """Get historical scanner results from scan store.

    Returns completed scan results with candidates and metrics.
    Uses real DuckDB scan_store for persistence.
    """
    try:
        scans = get_recent_scans(scanner=scanner_name, limit=limit)

        # Filter by date if provided
        if date:
            from datetime import date as date_type

            target_date = date_type.fromisoformat(date)
            scans = [
                s
                for s in scans
                if hasattr(s.get("scanned_at"), "date") and s["scanned_at"].date() == target_date
            ]

        return {
            "scans": [
                {
                    "scan_id": s["scan_id"],
                    "scanner": s["scanner"],
                    "scanned_at": s["scanned_at"].isoformat()
                    if hasattr(s["scanned_at"], "isoformat")
                    else str(s["scanned_at"]),
                    "universe_size": s["universe_size"],
                }
                for s in scans
            ],
            "count": len(scans),
        }
    except Exception as exc:
        logger.error("Scan results fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan results fetch failed: {exc!s}",
        ) from exc


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

        query = (
            "SELECT symbol, ltp, intraday_score, signal, trend, "
            "momentum_5d_pct, roc_5, relative_volume, day_high, day_low, day_volume "
            f"FROM {view_name} "
            "LIMIT ?"
        )

        results = vm.query(query, [limit]).fetchall()

        candidates = []
        for row in results:
            candidates.append(
                ScannerSnapshot(
                    symbol=row[0],
                    ltp=float(row[1]) if row[1] else 0.0,
                    intraday_score=float(row[2]) if row[2] else 0.0,
                    signal=row[3] or "NEUTRAL",
                    trend=row[4] or "Neutral",
                    momentum_5d_pct=float(row[5]) if row[5] is not None else None,
                    roc_5=float(row[6]) if row[6] else None,
                    relative_volume=float(row[7]) if row[7] else None,
                    day_high=float(row[8]) if row[8] else None,
                    day_low=float(row[9]) if row[9] else None,
                    day_volume=float(row[10]) if row[10] else None,
                )
            )

        return ScannerCandidatesResponse(
            candidates=candidates,
            count=len(candidates),
        )

    except Exception as exc:
        logger.error("Top candidates fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Top candidates fetch failed: {exc!s}",
        ) from exc


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
                   momentum_5d_pct, roc_5, relative_volume, day_high, day_low, day_volume
            FROM v_intraday_snapshot
            ORDER BY intraday_score DESC
            LIMIT ?
        """

        results = vm.query(query, [limit]).fetchall()

        candidates = []
        for row in results:
            candidates.append(
                ScannerSnapshot(
                    symbol=row[0],
                    ltp=float(row[1]) if row[1] else 0.0,
                    intraday_score=float(row[2]) if row[2] else 0.0,
                    signal=row[3] or "NEUTRAL",
                    trend=row[4] or "Neutral",
                    momentum_5d_pct=float(row[5]) if row[5] is not None else None,
                    roc_5=float(row[6]) if row[6] else None,
                    relative_volume=float(row[7]) if row[7] else None,
                    day_high=float(row[8]) if row[8] else None,
                    day_low=float(row[9]) if row[9] else None,
                    day_volume=float(row[10]) if row[10] else None,
                )
            )

        return ScannerCandidatesResponse(
            candidates=candidates,
            count=len(candidates),
        )

    except Exception as exc:
        logger.error("Snapshot fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot fetch failed: {exc!s}",
        ) from exc


@router.post("/run", response_model=dict)
async def run_scan(
    scanner_name: str = Query(..., description="Scanner to run"),
    universe: str = Query("NIFTY500", description="Universe to scan"),
    gateway=Depends(get_datalake_gateway),
    catalog=Depends(get_data_catalog),
):
    """Trigger a new scanner run.

    Executes ScannerRunner.run_all() for the specified scanner
    and universe. Returns scan ID for result retrieval.
    Uses real ScannerRunner with scanner implementations.
    """
    try:
        if gateway is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Data lake gateway not connected.",
            )

        ctx = get_trading_context()
        event_bus = ctx.event_bus if ctx else None

        from analytics.pipeline.pipeline import FeaturePipeline
        from analytics.scanner import BreakoutScanner, MomentumScanner, VolumeScanner

        pipeline = FeaturePipeline()

        scanner_map = {
            "momentum": lambda: MomentumScanner(pipeline, event_bus=event_bus),
            "volume": lambda: VolumeScanner(pipeline, event_bus=event_bus),
            "breakout": lambda: BreakoutScanner(pipeline, event_bus=event_bus),
        }

        if scanner_name.lower() not in scanner_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown scanner '{scanner_name}'. Available: {', '.join(scanner_map.keys())}",
            )

        scanners = [scanner_map[scanner_name.lower()]()]

        from datalake.research.scanner_universe import load_scanner_universe

        universe_df, load_stats = load_scanner_universe(
            gateway,
            catalog,
            universe,
            timeframe="1m",
        )

        if universe_df.empty:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Universe data not available for '{universe}'. "
                    f"requested={load_stats['requested']} loaded={load_stats['loaded']}"
                ),
                headers={"Retry-After": "60"},
            )

        from analytics.scanner.runner import ScannerRunner

        runner = ScannerRunner(max_workers=4, timeout_seconds=30.0)
        results = runner.run_all(scanners, universe_df)

        scan_ids = []
        for result in results:
            if result.success and result.scan_result:
                scan_id = save_scan_result(
                    scanner=result.scanner_name,
                    candidates=result.scan_result.candidates,
                    universe_size=result.scan_result.universe_size,
                    metadata={
                        "universe": universe,
                        "load_stats": load_stats,
                    },
                )
                scan_ids.append(scan_id)

        if not scan_ids:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Scanner execution failed to produce results",
            )

        return {
            "scan_id": scan_ids[0],
            "scan_ids": scan_ids,
            "status": "completed",
            "scanner": scanner_name,
            "universe": universe,
            "timestamp": datetime.now().isoformat(),
            "candidate_count": sum(r.candidate_count for r in results if r.success),
            "universe_stats": load_stats,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Scanner run failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scanner run failed: {exc!s}",
        ) from exc
