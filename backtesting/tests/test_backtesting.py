import pytest


class Trade:
    def __init__(self, entry_price: float, exit_price: float, quantity: int, is_long: bool):
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.quantity = quantity
        self.is_long = is_long

    @property
    def pnl(self) -> float:
        direction = 1 if self.is_long else -1
        return (self.exit_price - self.entry_price) * self.quantity * direction


class BacktestAnalyzer:
    """Mock Backtesting Performance Analyzer for isolation testing."""

    def calculate_metrics(self, trades: list[Trade]) -> dict[str, float]:
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0}

        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]

        gross_profits = sum(t.pnl for t in winning_trades)
        gross_losses = abs(sum(t.pnl for t in losing_trades))

        win_rate = len(winning_trades) / len(trades)
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else float("inf")

        return {
            "total_trades": len(trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_pnl": sum(t.pnl for t in trades),
        }

    def calculate_max_drawdown(self, initial_capital: float, trades: list[Trade]) -> float:
        equity = initial_capital
        peak = initial_capital
        max_dd = 0.0

        for trade in trades:
            equity += trade.pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        return max_dd


# ── Tests ──────────────────────────────────────────────────────────────────


def test_trade_pnl_calculation():
    long_trade = Trade(entry_price=100.0, exit_price=105.0, quantity=10, is_long=True)
    assert long_trade.pnl == 50.0  # (105 - 100) * 10 = 50

    short_trade = Trade(entry_price=100.0, exit_price=105.0, quantity=10, is_long=False)
    assert short_trade.pnl == -50.0  # (100 - 105) * 10 = -50


def test_backtesting_metrics_calculations():
    analyzer = BacktestAnalyzer()
    trades = [
        Trade(100.0, 105.0, 10, is_long=True),  # PnL = +50
        Trade(100.0, 98.0, 10, is_long=True),  # PnL = -20
        Trade(50.0, 48.0, 20, is_long=False),  # PnL = +40
    ]

    metrics = analyzer.calculate_metrics(trades)
    assert metrics["total_trades"] == 3
    assert metrics["win_rate"] == pytest.approx(2 / 3)
    assert metrics["total_pnl"] == 70.0
    # Profit factor: (50 + 40) / 20 = 4.5
    assert metrics["profit_factor"] == 4.5


def test_max_drawdown_calculation():
    analyzer = BacktestAnalyzer()
    # Starting capital: 10,000
    # Trade 1: PnL = -1,000 (Equity: 9,000, Peak: 10,000, DD: 10%)
    # Trade 2: PnL = +2,000 (Equity: 11,000, Peak: 11,000, DD: 0%)
    # Trade 3: PnL = -3,000 (Equity: 8,000, Peak: 11,000, DD: 27.27%)
    trades = [
        Trade(100.0, 90.0, 100, is_long=True),
        Trade(100.0, 120.0, 100, is_long=True),
        Trade(100.0, 70.0, 100, is_long=True),
    ]

    max_dd = analyzer.calculate_max_drawdown(initial_capital=10000.0, trades=trades)
    assert max_dd == pytest.approx(3000.0 / 11000.0)
