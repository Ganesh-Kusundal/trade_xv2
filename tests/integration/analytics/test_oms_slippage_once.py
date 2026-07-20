"""Phase 1 zero-parity: OMS path applies slippage exactly once (F2a/F2d).

Uses a real port-compliant adapter (not MagicMock) so we can assert the price
handed to OMS without depending on unrelated OrderValidator/DomainEvent wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from analytics.oms_fill_price import resolve_oms_fill_price
from analytics.paper.models import PaperConfig, PaperSession
from analytics.paper.signal_processor import PaperSignalProcessor
from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.models import ReplayConfig, ReplaySession
from analytics.replay.signal_processor import SignalProcessor
from analytics.strategy.models import Signal, SignalType
from domain.candles.historical import HistoricalBar
from domain.trading_costs import apply_slippage


@dataclass
class _Fill:
    order_id: str
    price: Decimal


@dataclass
class CapturingOmsAdapter:
    """Minimal OmsBacktestAdapterPort: slip once, record fills like production."""

    slippage_pct: float = 0.0
    fills: list[_Fill] = field(default_factory=list)
    open_prices: list[Decimal] = field(default_factory=list)
    close_prices: list[Decimal] = field(default_factory=list)
    _n: int = 0

    def open_long(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        *,
        strategy: str | None = None,
        reasons: list[str] | None = None,
    ) -> str | None:
        self.open_prices.append(price)
        self._n += 1
        oid = f"cap-open-{self._n}"
        fill_px = apply_slippage(price, side="BUY", slippage_pct=self.slippage_pct)
        self.fills.append(_Fill(order_id=oid, price=fill_px))
        return oid

    def close_long(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        *,
        strategy: str | None = None,
        reasons: list[str] | None = None,
    ) -> str | None:
        self.close_prices.append(price)
        self._n += 1
        oid = f"cap-close-{self._n}"
        fill_px = apply_slippage(price, side="SELL", slippage_pct=self.slippage_pct)
        self.fills.append(_Fill(order_id=oid, price=fill_px))
        return oid

    def modify_order(self, order_id: str, **kwargs: Any) -> bool:
        return False

    def cancel_order(self, order_id: str) -> bool:
        return False

    def get_position(self, symbol: str, exchange: str = "NSE") -> dict | None:
        return None

    def get_orders(self) -> list:
        return []


def _bar(close: float = 100.0) -> HistoricalBar:
    return HistoricalBar.from_replay(
        symbol="TEST",
        timestamp=datetime(2026, 1, 2, 9, 20, tzinfo=timezone.utc),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=10_000,
    )


def _buy_signal() -> Signal:
    return Signal(
        symbol="TEST",
        signal_type=SignalType.BUY,
        confidence=0.9,
        strategy="once_slip",
    )


def test_paper_signal_processor_passes_unslipped_price_into_oms() -> None:
    """Paper must not pre-slip; adapter slips once (fill ≈ 100.1, not ≈ 100.2001)."""
    slip_pct = 0.1
    base = Decimal("100")
    once = float(apply_slippage(base, side="BUY", slippage_pct=slip_pct))
    twice = float(apply_slippage(Decimal(str(once)), side="BUY", slippage_pct=slip_pct))

    adapter = CapturingOmsAdapter(slippage_pct=slip_pct)
    config = PaperConfig(
        initial_capital=100_000,
        max_position_pct=100.0,
        slippage_pct=slip_pct,
        commission_flat=0.0,
        max_positions=5,
    )
    recorded: list[float] = []

    def record_fill(session, **kwargs):
        recorded.append(float(kwargs["price"]))
        return True

    processor = PaperSignalProcessor(config, record_fill, oms_adapter=adapter)
    session = PaperSession(capital=config.initial_capital)
    processor.process(_buy_signal(), _bar(close=100.0), session)

    assert adapter.open_prices == [base], "paper must pass un-slipped base into OMS"
    assert recorded and abs(recorded[0] - once) < 1e-9
    assert abs(recorded[0] - twice) > 1e-6
    assert abs(float(adapter.fills[-1].price) - once) < 1e-9


def test_replay_oms_session_records_slipped_fill_price() -> None:
    """Replay session must book OMS fill price (slipped once), not un-slipped base."""
    slip_pct = 0.1
    base = Decimal("100")
    once = float(apply_slippage(base, side="BUY", slippage_pct=slip_pct))

    adapter = CapturingOmsAdapter(slippage_pct=slip_pct)
    config = ReplayConfig(
        initial_capital=100_000,
        max_position_pct=100.0,
        slippage_pct=slip_pct,
        commission_flat=0.0,
    )
    recorder = FillRecorder(config)
    processor = SignalProcessor(recorder, oms_adapter=adapter)
    session = ReplaySession(capital=config.initial_capital)
    processor.process(_buy_signal(), _bar(close=100.0), session, config)

    assert adapter.open_prices == [base]
    assert session.has_position("TEST")
    pos = session._to_simulated_position("TEST")
    assert pos is not None
    assert abs(pos.entry_price - once) < 1e-9

    booked = resolve_oms_fill_price(
        adapter,
        adapter.fills[-1].order_id,
        base_price=base,
        side="BUY",
        slippage_pct=slip_pct,
    )
    assert abs(booked - once) < 1e-9
