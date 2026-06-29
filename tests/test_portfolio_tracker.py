"""Tests for application.oms.portfolio_tracker — OMS-backed portfolio state."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from application.oms.portfolio_tracker import PortfolioSnapshot, PortfolioTracker
from domain import Position, Trade
from domain.types import Side


class TestPortfolioTracker:
    """Test PortfolioTracker reads from OMS correctly."""

    def _make_tracker(self, initial_capital=Decimal("100000")):
        """Create a tracker with mock OMS."""
        oms = Mock()
        position_manager = Mock()
        position_manager.get_all_positions.return_value = []
        position_manager.get_position.return_value = None
        return PortfolioTracker(oms, position_manager, initial_capital)

    def test_initial_capital(self):
        tracker = self._make_tracker(Decimal("50000"))
        assert tracker.get_capital() == Decimal("50000")

    def test_positions_from_oms(self):
        tracker = self._make_tracker()
        pos = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500"))
        tracker._positions.get_all_positions.return_value = [pos]
        positions = tracker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"

    def test_capital_updates_on_buy(self):
        tracker = self._make_tracker(Decimal("100000"))
        trade = Trade(
            trade_id="T1", order_id="O1",
            symbol="RELIANCE", exchange="NSE", side=Side.BUY,
            quantity=10, price=Decimal("2500"), trade_value=Decimal("25000"),
        )
        tracker.on_trade_applied(trade)
        # Capital decreased by 10 * 2500 = 25000
        assert tracker.get_capital() == Decimal("75000")

    def test_capital_updates_on_sell(self):
        tracker = self._make_tracker(Decimal("75000"))
        trade = Trade(
            trade_id="T2", order_id="O2",
            symbol="RELIANCE", exchange="NSE", side=Side.SELL,
            quantity=10, price=Decimal("2600"), trade_value=Decimal("26000"),
        )
        tracker.on_trade_applied(trade)
        # Capital increased by 10 * 2600 = 26000
        assert tracker.get_capital() == Decimal("101000")
        # trade_value - (quantity * price) = 26000 - 26000 = 0
        assert tracker._realized_pnl == Decimal("0")

    def test_equity_calculation(self):
        tracker = self._make_tracker(Decimal("100000"))
        pos = Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500"))
        tracker._positions.get_all_positions.return_value = [pos]
        tracker._realized_pnl = Decimal("5000")

        equity = tracker.get_equity(current_prices={"RELIANCE": Decimal("2600")})
        # 100000 + 5000 + (2600-2500)*10 = 106000
        assert equity == Decimal("106000")

    def test_snapshot(self):
        tracker = self._make_tracker(Decimal("100000"))
        snapshot = tracker.snapshot()
        assert isinstance(snapshot, PortfolioSnapshot)
        assert snapshot.capital == Decimal("100000")
        assert snapshot.equity == Decimal("100000")

    def test_trades_accumulated(self):
        tracker = self._make_tracker()
        for i in range(3):
            trade = Trade(
                trade_id=f"T{i}", order_id=f"O{i}",
                symbol="RELIANCE", exchange="NSE", side=Side.BUY,
                quantity=10, price=Decimal("2500"), trade_value=Decimal("25000"),
            )
            tracker.on_trade_applied(trade)
        assert len(tracker.get_trades()) == 3
