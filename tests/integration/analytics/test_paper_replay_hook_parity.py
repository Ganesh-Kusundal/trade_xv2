"""WS-H / ADR-0024: paper vs replay SignalProcessor hook parity contract.

Asserts documented intentional differences between
``analytics.paper.signal_processor`` and ``analytics.replay.signal_processor``
hooks — not that they are identical.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analytics.paper.models import PaperConfig, PaperPosition, PaperSession, PositionSide
from analytics.paper.signal_processor import PaperSignalProcessor
from analytics.replay.models import ReplayConfig, ReplaySession, SimulatedPosition
from analytics.replay.signal_processor import SignalProcessor as ReplaySignalProcessor
from analytics.simulation.fill_recorder import FillRecorder
from application.services.trading_costs_service import SlippageModel
from domain.candles.historical import HistoricalBar


def _bar(*, close: float = 100.0, volume: float = 10_000) -> HistoricalBar:
    return HistoricalBar.from_replay(
        symbol="TEST",
        timestamp=datetime(2026, 1, 2, 9, 20, tzinfo=timezone.utc),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=volume,
    )


def _paper_hooks(**config_kw):
    config = PaperConfig(**config_kw)
    processor = PaperSignalProcessor(config, record_fill=lambda *a, **k: True)
    return processor._build_hooks(), config


def _replay_hooks(**config_kw):
    config = ReplayConfig(**config_kw)
    recorder = FillRecorder(config)
    processor = ReplaySignalProcessor(recorder)
    return processor._build_hooks(), config


def _seed_paper_position(session: PaperSession, *, cash: float = 80_000) -> None:
    session.capital = cash
    t0 = datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc)
    session.bootstrap_position(
        PaperPosition(
            symbol="TEST",
            side=PositionSide.LONG,
            entry_price=100.0,
            quantity=200,
            entry_time=t0,
            current_price=100.0,
        )
    )


def _seed_replay_position(session: ReplaySession, *, cash: float = 80_000) -> None:
    session.capital = cash
    session.position = SimulatedPosition(
        symbol="TEST",
        side="BUY",
        entry_price=100.0,
        quantity=200,
        entry_time=datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc),
        mark_price=100.0,
    )


class TestEntryGateParity:
    """ADR-0024 §1: replay never gates; paper enforces session limits."""

    def test_replay_entry_gate_always_false(self) -> None:
        hooks, config = _replay_hooks()
        session = ReplaySession(capital=100_000)
        _seed_replay_position(session)

        assert hooks.entry_gate(session, config, via_oms=False, symbol="TEST") is False
        assert hooks.entry_gate(session, config, via_oms=True, symbol="TEST") is False

    def test_paper_blocks_at_max_positions(self) -> None:
        hooks, config = _paper_hooks(max_positions=1)
        session = PaperSession(capital=100_000)
        _seed_paper_position(session, cash=80_000)

        assert hooks.entry_gate(session, config, via_oms=False, symbol="NEW") is True
        assert hooks.entry_gate(session, config, via_oms=True, symbol="NEW") is True

    def test_paper_allows_entry_when_under_limits(self) -> None:
        hooks, config = _paper_hooks(max_positions=5, max_daily_loss_pct=0.0)
        session = PaperSession(capital=100_000)

        assert hooks.entry_gate(session, config, via_oms=False, symbol="TEST") is False
        assert hooks.entry_gate(session, config, via_oms=True, symbol="TEST") is False

    def test_paper_daily_loss_gate_oms_only(self) -> None:
        hooks, config = _paper_hooks(max_positions=5, max_daily_loss_pct=2.0)
        session = PaperSession(capital=100_000)
        session.daily_pnl = -3_000.0  # 3% of equity > 2% limit

        assert hooks.entry_gate(session, config, via_oms=False, symbol="TEST") is False
        assert hooks.entry_gate(session, config, via_oms=True, symbol="TEST") is True


class TestEquityForSizingParity:
    """ADR-0024 §2: paper uses cash; replay uses mark-to-market equity."""

    def test_flat_session_equity_basis_matches(self) -> None:
        paper_hooks, _ = _paper_hooks()
        replay_hooks, _ = _replay_hooks()
        paper_session = PaperSession(capital=100_000)
        replay_session = ReplaySession(capital=100_000)

        assert paper_hooks.equity_for_sizing(paper_session) == 100_000
        assert replay_hooks.equity_for_sizing(replay_session) == 100_000

    def test_open_position_diverges_by_design(self) -> None:
        paper_hooks, _ = _paper_hooks()
        replay_hooks, _ = _replay_hooks()
        paper_session = PaperSession(capital=100_000)
        replay_session = ReplaySession(capital=100_000)
        _seed_paper_position(paper_session, cash=80_000)
        _seed_replay_position(replay_session, cash=80_000)

        assert paper_hooks.equity_for_sizing(paper_session) == 80_000
        assert replay_hooks.equity_for_sizing(replay_session) == 100_000


class TestPositionViewParity:
    """ADR-0024 §3: same projector, mode-specific view types."""

    def test_paper_position_view_type(self) -> None:
        hooks, _ = _paper_hooks()
        session = PaperSession(capital=100_000)
        _seed_paper_position(session)

        view = hooks.position_view(session, "TEST")
        assert isinstance(view, PaperPosition)
        assert view.symbol == "TEST"
        assert view.quantity == 200

    def test_replay_position_view_type(self) -> None:
        hooks, _ = _replay_hooks()
        session = ReplaySession(capital=100_000)
        _seed_replay_position(session)

        view = hooks.position_view(session, "TEST")
        assert isinstance(view, SimulatedPosition)
        assert view.symbol == "TEST"
        assert view.quantity == 200


class TestSlippagePctParity:
    """ADR-0024 §4: paper fixed pct; replay model-aware on pure-sim hook."""

    def test_paper_slippage_is_fixed_config(self) -> None:
        hooks, _ = _paper_hooks(slippage_pct=0.42)
        session = PaperSession(capital=100_000)

        low_vol = hooks.slippage_pct(session, _bar(volume=1_000))
        high_vol = hooks.slippage_pct(session, _bar(volume=1_000_000))
        assert low_vol == pytest.approx(0.42)
        assert high_vol == pytest.approx(0.42)

    def test_replay_fixed_pct_matches_base(self) -> None:
        hooks, _ = _replay_hooks(slippage_pct=0.42, slippage_model=SlippageModel.FIXED_PCT)
        session = ReplaySession(capital=100_000)

        assert hooks.slippage_pct(session, _bar(volume=50_000)) == pytest.approx(0.42)

    def test_replay_volume_weighted_scales_with_bar_volume(self) -> None:
        hooks, _ = _replay_hooks(
            slippage_pct=0.1,
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            avg_volume=100_000,
        )
        session = ReplaySession(capital=100_000)

        thin = hooks.slippage_pct(session, _bar(volume=50_000))
        thick = hooks.slippage_pct(session, _bar(volume=200_000))
        assert thin == pytest.approx(0.2)  # 0.1 * (100k / 50k)
        assert thick == pytest.approx(0.05)  # 0.1 * (100k / 200k)
        assert thin > thick

    def test_oms_slippage_hook_same_fixed_pct_both_modes(self) -> None:
        paper_hooks, paper_cfg = _paper_hooks(slippage_pct=0.15)
        replay_hooks, replay_cfg = _replay_hooks(
            slippage_pct=0.15,
            slippage_model=SlippageModel.VOLUME_WEIGHTED,
            avg_volume=100_000,
        )

        assert paper_hooks.oms_slippage_pct(paper_cfg) == pytest.approx(0.15)
        assert replay_hooks.oms_slippage_pct(replay_cfg) == pytest.approx(0.15)
