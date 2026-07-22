"""Datalake maintenance endpoints — manual sync trigger."""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from interface.api.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])

_lock = threading.Lock()
_running = False
_last_report: dict[str, Any] | None = None


def _run_sync(
    timeframe: str,
    workers: int,
    limit: int | None,
    skip_health_check: bool,
    repair_scope: str,
) -> None:
    global _running, _last_report
    try:
        from runtime.datalake_sync import run_federated_sync

        report = run_federated_sync(
            timeframe=timeframe,
            workers=workers,
            limit=limit,
            print_fn=logger.info,
            run_health_check=not skip_health_check,
            repair_scope=repair_scope,
        )
        with _lock:
            _last_report = report.as_dict()
    except Exception as exc:
        logger.exception("datalake_sync_background_failed")
        with _lock:
            _last_report = {"ok": False, "error": str(exc)}
    finally:
        with _lock:
            _running = False


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED, summary="Trigger a datalake sync")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    timeframe: str = "1m",
    workers: int = 10,
    limit: int | None = None,
    skip_health_check: bool = False,
    repair_scope: str = "tail",
) -> dict[str, Any]:
    """Sync every registered symbol up to today (federated, quota-aware).

    ``repair_scope``: ``tail`` (default, fast daily), ``internal`` (gap backfill),
    or ``all`` (both). Runs in the background — poll ``GET /sync/status``.
    """
    if repair_scope not in ("tail", "internal", "all"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repair_scope must be tail, internal, or all",
        )
    global _running
    with _lock:
        if _running:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A sync is already running"
            )
        _running = True
    background_tasks.add_task(
        _run_sync, timeframe, workers, limit, skip_health_check, repair_scope
    )
    return {
        "status": "started",
        "timeframe": timeframe,
        "workers": workers,
        "limit": limit,
        "repair_scope": repair_scope,
    }


@router.get("/sync/status", summary="Status of the most recent (or in-progress) sync")
async def sync_status() -> dict[str, Any]:
    with _lock:
        return {"running": _running, "last_report": _last_report}
