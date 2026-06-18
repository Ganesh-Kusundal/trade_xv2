"""Replay endpoints (sessions, controls, market feed)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from datalake.api.schemas import (
    CreateReplaySessionRequest,
    ReplaySessionResponse,
    ReplayControlRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store (TODO: Replace with proper state management)
_sessions: dict[str, dict] = {}


@router.get("/sessions", response_model=dict)
async def list_sessions():
    """List all replay sessions (active and historical)."""
    return {
        "sessions": list(_sessions.values()),
        "count": len(_sessions),
    }


@router.post("/sessions", response_model=ReplaySessionResponse)
async def create_session(req: CreateReplaySessionRequest):
    """Create a new replay session.
    
    Initializes replay engine and returns session handle.
    """
    session_id = f"replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    session = {
        "session_id": session_id,
        "date": req.date,
        "universe": req.universe,
        "speed": req.speed,
        "status": "initialized",
        "created_at": datetime.now().isoformat(),
        "progress": 0.0,
    }
    
    _sessions[session_id] = session
    
    return ReplaySessionResponse(
        session_id=session_id,
        status=session["status"],
        date=req.date,
        universe=req.universe,
        speed=req.speed,
        progress=0.0,
    )


@router.get("/sessions/{session_id}", response_model=ReplaySessionResponse)
async def get_session(session_id: str):
    """Get replay session details."""
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )
    
    return ReplaySessionResponse(
        session_id=session_id,
        status=session["status"],
        date=session["date"],
        universe=session["universe"],
        speed=session["speed"],
        progress=session["progress"],
    )


@router.post("/sessions/{session_id}/play", response_model=ReplaySessionResponse)
async def play_session(session_id: str):
    """Start/resume replay playback.
    
    Begins streaming historical market data at the configured speed.
    """
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )
    
    session["status"] = "playing"
    
    # TODO: Start replay engine
    
    return ReplaySessionResponse(
        session_id=session_id,
        status="playing",
        date=session["date"],
        universe=session["universe"],
        speed=session["speed"],
        progress=session["progress"],
    )


@router.post("/sessions/{session_id}/pause", response_model=ReplaySessionResponse)
async def pause_session(session_id: str):
    """Pause replay playback."""
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )
    
    session["status"] = "paused"
    
    # TODO: Pause replay engine
    
    return ReplaySessionResponse(
        session_id=session_id,
        status="paused",
        date=session["date"],
        universe=session["universe"],
        speed=session["speed"],
        progress=session["progress"],
    )


@router.post("/sessions/{session_id}/stop", response_model=ReplaySessionResponse)
async def stop_session(session_id: str):
    """Stop replay playback and clean up."""
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )
    
    session["status"] = "stopped"
    session["progress"] = 100.0
    
    # TODO: Stop replay engine and cleanup
    
    return ReplaySessionResponse(
        session_id=session_id,
        status="stopped",
        date=session["date"],
        universe=session["universe"],
        speed=session["speed"],
        progress=100.0,
    )


@router.post("/sessions/{session_id}/speed", response_model=ReplaySessionResponse)
async def set_speed(session_id: str, req: ReplayControlRequest):
    """Set replay playback speed (1x, 2x, 5x, 10x, 20x)."""
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )
    
    valid_speeds = [1, 2, 5, 10, 20]
    if req.speed not in valid_speeds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid speed '{req.speed}'. Valid: {', '.join(map(str, valid_speeds))}",
        )
    
    session["speed"] = req.speed
    
    # TODO: Update replay engine speed
    
    return ReplaySessionResponse(
        session_id=session_id,
        status=session["status"],
        date=session["date"],
        universe=session["universe"],
        speed=req.speed,
        progress=session["progress"],
    )


@router.post("/sessions/{session_id}/seek", response_model=ReplaySessionResponse)
async def seek_to_time(session_id: str, timestamp_ms: int = Query(...)):
    """Seek to a specific timestamp in the replay."""
    session = _sessions.get(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )
    
    # TODO: Seek replay engine to timestamp
    
    return ReplaySessionResponse(
        session_id=session_id,
        status=session["status"],
        date=session["date"],
        universe=session["universe"],
        speed=session["speed"],
        progress=session["progress"],
    )
