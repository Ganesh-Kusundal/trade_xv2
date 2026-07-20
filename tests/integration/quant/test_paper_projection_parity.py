"""P2: paper fills mirror PortfolioProjector."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from analytics.paper.engine import PaperTradingEngine
from analytics.paper.models import PaperConfig, PaperSession
from domain.candles.historical import HistoricalBar


@pytest.fixture
def paper_engine() -> PaperTradingEngine:
    adapter = MagicMock()
    adapter.open_long.return_value = "PAPER-1"
    adapter.close_long.return_value = "PAPER-2"
    return PaperTradingEngine(
        config=PaperConfig(initial_capital=100_000, slippage_pct=0.0, commission_flat=0.0),
        oms_adapter=adapter,
    )


def test_paper_open_close_matches_projector(paper_engine: PaperTradingEngine) -> None:
    session = PaperSession(capital=100_000)
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

    from analytics.strategy.models import Signal, SignalType

    buy = Signal(symbol="TEST", signal_type=SignalType.BUY, confidence=0.9, strategy="paper")
    paper_engine._process_signal_via_oms(buy, bar, session)

    assert session.has_position("TEST")
    proj = session.projector.get_position("TEST", "NSE")
    assert proj is not None
    assert proj.quantity > 0

    paper_engine._close_position("TEST", 105.0, ts, session, "test exit")
    assert not session.has_position("TEST")
    proj = session.projector.get_position("TEST", "NSE")
    assert proj is None or proj.quantity == 0
