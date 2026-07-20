"""Audit trail API endpoints.

Provides query access to the persistent audit event store.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from application.audit import audit_logger
from interface.api.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/events", summary="Query audit events")
async def list_audit_events(
    event_type: str | None = Query(None, description="Filter by event type"),
    actor: str | None = Query(None, description="Filter by actor"),
    from_time: str | None = Query(None, description="ISO timestamp lower bound (inclusive)"),
    to_time: str | None = Query(None, description="ISO timestamp upper bound (inclusive)"),
    limit: int = Query(100, ge=1, le=10000, description="Max events to return"),
) -> list[dict[str, Any]]:
    """Return audit events matching the given filters, newest first."""
    events = audit_logger.store.query(
        event_type=event_type,
        actor=actor,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
    )
    return [e.to_dict() for e in events]


@router.get("/events/{event_id}", summary="Get a single audit event")
async def get_audit_event(event_id: str) -> dict[str, Any]:
    """Retrieve a single audit event by its ID."""
    event = audit_logger.store.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return event.to_dict()


@router.get("/stats", summary="Audit event statistics")
async def audit_stats() -> dict[str, Any]:
    """Return event count and breakdown by event_type."""
    total = audit_logger.store.count()
    all_events = audit_logger.store.query(limit=10000)
    by_type: Counter[str] = Counter(e.event_type for e in all_events)
    return {
        "total": total,
        "by_event_type": dict(by_type.most_common()),
    }
