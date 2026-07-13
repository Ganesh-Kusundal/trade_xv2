"""Replay schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateReplaySessionRequest(BaseModel):
    """Create replay session request."""

    symbol: str
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    timeframe: str = "1m"
    from_t: int | None = None
    to_t: int | None = None
    universe: str = "NIFTY500"
    speed: int = 5


class ReplaySessionResponse(BaseModel):
    """Replay session state."""

    session_id: str
    status: str  # initialized, playing, paused, stopped
    date: str
    universe: str = "NIFTY500"
    speed: int = 5
    progress: float = 0.0


class ReplayControlRequest(BaseModel):
    """Replay control action."""

    action: str = Field(..., description="play, pause, step, seek, set_speed")
    n: int | None = Field(None, description="Steps for 'step' action")
    to_t: int | None = Field(None, description="Target timestamp for 'seek'")
    speed: int | None = Field(None, description="Speed multiplier for 'set_speed'")
