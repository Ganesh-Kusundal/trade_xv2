"""Tests for TradingSession VO."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from domain.sessions import TradingSession
from domain.sessions.trading_session import SessionStatus


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_frozen():
    ts = TradingSession(session_id="s1", started_at=_now())
    with pytest.raises(FrozenInstanceError):
        ts.status = SessionStatus.ACTIVE  # type: ignore[misc]


def test_default_status_pending():
    ts = TradingSession(session_id="s1", started_at=_now())
    assert ts.status == SessionStatus.PENDING
    assert not ts.is_active


def test_with_status():
    ts = TradingSession(session_id="s1", started_at=_now())
    active = ts.with_status(SessionStatus.ACTIVE)
    assert active.status == SessionStatus.ACTIVE
    assert active.is_active
    assert ts.status == SessionStatus.PENDING  # original unchanged


def test_with_ended():
    ts = TradingSession(session_id="s1", started_at=_now(), status=SessionStatus.ACTIVE)
    ended = ts.with_ended()
    assert ended.status == SessionStatus.ENDED
    assert ended.ended_at is not None
    assert ended.duration_seconds is not None
    assert ended.duration_seconds >= 0


def test_duration_none_when_not_ended():
    ts = TradingSession(session_id="s1", started_at=_now())
    assert ts.duration_seconds is None


def test_brokers_tuple():
    ts = TradingSession(session_id="s1", started_at=_now(), brokers=("dhan", "upstox"))
    assert ts.brokers == ("dhan", "upstox")
