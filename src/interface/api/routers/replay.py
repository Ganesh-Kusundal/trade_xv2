"""Replay endpoints (sessions, controls, market feed).

Uses a thread-safe session store instead of a module-level mutable dict
so that multiple workers or async tasks do not silently disagree about
session state.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from interface.api.auth import require_auth
from interface.api.schemas import (
    CreateReplaySessionRequest,
    ReplayControlRequest,
    ReplaySessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


class ReplaySessionStore:
    """Thread-safe in-memory store for replay sessions.

    Uses an RLock to protect against concurrent access from multiple
    async tasks or WebSocket handlers. This replaces the previous
    module-level mutable dict which was unsafe under concurrency.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: dict[str, dict] = {}

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            s = self._sessions.get(session_id)
            return dict(s) if s else None

    def put(self, session_id: str, session: dict) -> None:
        with self._lock:
            self._sessions[session_id] = dict(session)

    def update(self, session_id: str, **changes) -> dict | None:
        with self._lock:
            if session_id not in self._sessions:
                return None
            self._sessions[session_id].update(changes)
            return dict(self._sessions[session_id])

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list_all(self) -> list[dict]:
        with self._lock:
            return [dict(s) for s in self._sessions.values()]

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


_session_store = ReplaySessionStore()


def get_replay_session_store() -> ReplaySessionStore:
    """Return the process-wide replay session store."""
    return _session_store


def _build_response(session: dict) -> ReplaySessionResponse:
    """Build a ReplaySessionResponse from a session dict."""
    return ReplaySessionResponse(
        session_id=session["session_id"],
        status=session["status"],
        date=session.get("date", ""),
        universe=session.get("universe", ""),
        speed=session.get("speed", 1),
        progress=session.get("progress", 0.0),
    )


@router.get("/sessions", response_model=dict)
async def list_sessions():
    """List all replay sessions (active and historical)."""
    sessions = _session_store.list_all()
    return {
        "sessions": sessions,
        "count": len(sessions),
    }


@router.post("/sessions", response_model=ReplaySessionResponse)
async def create_session(req: CreateReplaySessionRequest):
    """Create a new replay session.

    Initializes replay engine and returns session handle.
    """
    import uuid

    session_id = f"replay_{uuid.uuid4().hex[:12]}"

    session = {
        "session_id": session_id,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "date": req.date,
        "universe": req.universe,
        "speed": req.speed,
        "status": "initialized",
        "created_at": datetime.now().isoformat(),
        "progress": 0.0,
    }

    _session_store.put(session_id, session)

    return _build_response(session)


@router.get("/sessions/{session_id}", response_model=ReplaySessionResponse)
async def get_session(session_id: str):
    """Get replay session details."""
    session = _session_store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )

    return _build_response(session)


@router.post("/sessions/{session_id}/play", response_model=ReplaySessionResponse)
async def play_session(session_id: str):
    """Start/resume replay playback.

    Begins streaming historical market data at the configured speed
    through the same FeaturePipeline + StrategyPipeline used in live trading.
    """
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )

    # State machine: cannot play a stopped or completed session
    current_status = session.get("status", "initialized")
    if current_status in ("stopped",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot play stopped session '{session_id}'. Create a new session.",
        )
    if current_status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session '{session_id}' already completed. Create a new session to replay again.",
        )

    _session_store.update(session_id, status="playing")

    # Load historical data and run replay engine
    try:
        from analytics.pipeline import ATR, RSI, SMA, FeaturePipeline
        from analytics.replay import ReplayConfig, ReplayEngine
        from analytics.strategy import MomentumStrategy, StrategyPipeline
        from interface.api.deps import get_container

        container = get_container()
        gateway = container.datalake_gateway if container else None
        if gateway is None:
            logger.warning("Data lake gateway not available — replay will be mock")
            session = _session_store.get(session_id) or session
            return _build_response(session)

        # Build pipeline (same as live trading for parity)
        pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
        strategy = StrategyPipeline(strategies=[MomentumStrategy()])
        config = ReplayConfig(
            initial_capital=100_000,
            warmup_bars=20,
            publish_events=True,
        )

        # Use session's stored configuration (from CreateReplaySessionRequest)
        symbol = session.get("symbol", "RELIANCE")
        timeframe = session.get("timeframe", "1m")

        df = gateway.history(
            symbol=symbol,
            exchange="NSE",
            timeframe=timeframe,
            lookback_days=1,
        )

        if df is None or (hasattr(df, "empty") and df.empty):
            logger.warning("No data loaded for %s on timeframe=%s", symbol, timeframe)
            session = _session_store.get(session_id) or session
            return _build_response(session)

        trading_context = getattr(container, "trading_context", None)
        if trading_context is not None:
            engine = ReplayEngine(
                pipeline,
                strategy,
                config,
                trading_context=trading_context,
            )
        else:
            engine = ReplayEngine(
                pipeline,
                strategy,
                config,
                allow_simulate_without_oms=True,
            )
        result = engine.run(df, symbol=symbol)

        # Store engine reference for lifecycle management
        session_update = _session_store.get(session_id)
        if session_update:
            session_update["_engine"] = engine

        total_bars = max(int(df.shape[0]), 1)
        _session_store.update(
            session_id,
            status="completed",
            progress=min(100.0, float(result.bars_processed / total_bars * 100)),
            bars_processed=result.bars_processed,
            signals_generated=result.signals_generated,
            total_trades=result.session.total_trades,
        )
        logger.info(
            "Replay completed: %d/%d bars, %d signals, %d trades on %s",
            result.bars_processed,
            total_bars,
            result.signals_generated,
            result.session.total_trades,
            symbol,
        )

    except Exception as exc:
        logger.error("Replay engine failed: %s", exc)
        _session_store.update(session_id, status="error")

    session = _session_store.get(session_id) or session
    return _build_response(session)


@router.post("/sessions/{session_id}/pause", response_model=ReplaySessionResponse)
async def pause_session(session_id: str):
    """Pause replay playback."""
    session = _session_store.update(session_id, status="paused")
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )

    return _build_response(session)


@router.post("/sessions/{session_id}/stop", response_model=ReplaySessionResponse)
async def stop_session(session_id: str):
    """Stop replay playback and clean up."""
    session = _session_store.update(session_id, status="stopped", progress=100.0)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )

    return _build_response(session)


@router.post("/sessions/{session_id}/speed", response_model=ReplaySessionResponse)
async def set_speed(session_id: str, req: ReplayControlRequest):
    """Set replay playback speed (1x, 2x, 5x, 10x, 20x)."""
    valid_speeds = [1, 2, 5, 10, 20]
    if req.speed not in valid_speeds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid speed '{req.speed}'. Valid: {', '.join(map(str, valid_speeds))}",
        )

    session = _session_store.update(session_id, speed=req.speed)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )

    return _build_response(session)


@router.post("/sessions/{session_id}/seek", response_model=ReplaySessionResponse)
async def seek_to_time(session_id: str, timestamp_ms: int = Query(...)):
    """Seek to a specific timestamp in the replay.

    Calculates progress as a percentage of the session date range.
    Falls back to a simple progress estimate if date range is unknown.
    """
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found",
        )

    # Calculate approximate progress based on timestamp
    # For now, use a simple estimate: assume session covers market hours (9:15-15:30 IST = 22500s)
    # The timestamp_ms represents milliseconds since epoch
    from datetime import timezone

    session_date_str = session.get("date", "")
    progress: float = 0.0
    if session_date_str:
        try:
            session_start = datetime.fromisoformat(session_date_str).replace(
                hour=9, minute=15, second=0, tzinfo=timezone.utc
            )
            session_end = session_start.replace(hour=15, minute=30, second=0)
            total_duration_ms = (session_end - session_start).total_seconds() * 1000
            if total_duration_ms > 0:
                elapsed_ms = max(0, timestamp_ms - session_start.timestamp() * 1000)
                progress = min(100.0, (elapsed_ms / total_duration_ms) * 100.0)
        except (ValueError, OSError):
            progress = 50.0  # fallback

    session = _session_store.update(session_id, progress=round(progress, 2))
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay session '{session_id}' not found after seek",
        )

    return _build_response(session)
