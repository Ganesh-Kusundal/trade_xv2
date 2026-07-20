"""P2 dual-projection evidence — replay simulated fills vs PortfolioProjector."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig, ReplaySession
from analytics.strategy.models import Signal, SignalType
from domain.candles.historical import HistoricalBar


def _session_signed_qty(session: ReplaySession, symbol: str) -> int:
    pos = session.fill_pipeline.projector.get_position(symbol, "NSE")
    return pos.quantity if pos is not None else 0


def _projector_signed_qty(session: ReplaySession, symbol: str) -> int:
    if session.projector is None:
        return 0
    pos = session.projector.get_position(symbol, "NSE")
    return pos.quantity if pos is not None else 0


def _assert_projection_parity(session: ReplaySession, symbol: str) -> None:
    assert _session_signed_qty(session, symbol) == _projector_signed_qty(session, symbol)


@pytest.fixture
def simulated_engine() -> ReplayEngine:
    return ReplayEngine(
        config=ReplayConfig(
            initial_capital=100_000,
            slippage_pct=0.0,
            commission_flat=0.0,
            max_position_pct=100.0,
        ),
        allow_simulate_without_oms=True,
    )


def test_simulated_round_trip_projector_matches_session(simulated_engine: ReplayEngine) -> None:
    """Buy then sell via simulated path — projector qty tracks session positions."""
    session = ReplaySession(capital=100_000)
    config = simulated_engine._config
    ts = datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc)
    bar = HistoricalBar.from_replay(
        symbol="TEST",
        timestamp=ts,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=10_000.0,
    )

    buy = Signal(
        symbol="TEST",
        signal_type=SignalType.BUY,
        confidence=0.9,
        strategy="parity",
    )
    simulated_engine._process_signal_simulated(buy, bar, session, config)
    assert session.has_position("TEST")
    _assert_projection_parity(session, "TEST")

    sell = Signal(
        symbol="TEST",
        signal_type=SignalType.SELL,
        confidence=0.9,
        strategy="parity",
    )
    simulated_engine._process_signal_simulated(sell, bar, session, config)
    assert not session.has_position("TEST")
    assert len(session.trades) == 1
    _assert_projection_parity(session, "TEST")
    assert _projector_signed_qty(session, "TEST") == 0
