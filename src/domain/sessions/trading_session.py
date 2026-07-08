"""TradingSession value object — captures a user's trading session lifecycle.

A TradingSession tracks when a user started trading, their session status,
and which brokers are active during the session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(str, Enum):
    """Trading session lifecycle status."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


@dataclass(frozen=True)
class TradingSession:
    """Immutable trading session descriptor."""

    session_id: str
    started_at: datetime
    status: SessionStatus = SessionStatus.PENDING
    brokers: tuple[str, ...] = ()
    ended_at: datetime | None = None

    def with_status(self, status: SessionStatus) -> TradingSession:
        return TradingSession(
            session_id=self.session_id,
            started_at=self.started_at,
            status=status,
            brokers=self.brokers,
            ended_at=self.ended_at,
        )

    def with_ended(self) -> TradingSession:
        return TradingSession(
            session_id=self.session_id,
            started_at=self.started_at,
            status=SessionStatus.ENDED,
            brokers=self.brokers,
            ended_at=datetime.now(timezone.utc),
        )

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()
