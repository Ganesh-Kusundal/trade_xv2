"""Paper Trading models — PaperConfig, PaperSession, PaperOrder, PaperPosition, PaperTrade, PaperResult.

Paper Trading runs the same FeaturePipeline + StrategyPipeline as live/replay/backtest,
but simulates order execution with realistic fills (slippage, commission).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from domain.enums import OrderStatus


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


# ---------------------------------------------------------------------------
# PaperConfig
# ---------------------------------------------------------------------------


@dataclass
class PaperConfig:
    """Configuration for paper trading session.

    Parameters
    ----------
    initial_capital:
        Starting capital (INR).
    max_position_pct:
        Max % of equity per position.
    max_positions:
        Max simultaneous open positions.
    slippage_pct:
        Simulated slippage as % of price.
    commission_pct:
        Commission as % of trade value (0.0003 = 0.03%).
    commission_flat:
        Flat commission per trade (added on top of percentage).
    warmup_bars:
        Bars to skip before generating signals.
    window_size:
        Sliding window size for feature computation (0 = unlimited).
    stop_loss_pct:
        Auto stop-loss as % from entry (0.0 = disabled).
    take_profit_pct:
        Auto take-profit as % from entry (0.0 = disabled).
    max_daily_loss_pct:
        Max daily loss as % of equity (0.0 = disabled).
    """

    initial_capital: float = 100_000.0
    max_position_pct: float = 25.0
    max_positions: int = 5
    slippage_pct: float = 0.01
    commission_pct: float = 0.0003
    commission_flat: float = 0.0
    warmup_bars: int = 20
    window_size: int = 100
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 0.0
    max_daily_loss_pct: float = 0.0


# ---------------------------------------------------------------------------
# PaperOrder
# ---------------------------------------------------------------------------


@dataclass
class PaperOrder:
    """A simulated order in paper trading."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    order_time: datetime
    status: OrderStatus = OrderStatus.OPEN
    fill_price: float = 0.0
    fill_time: datetime | None = None
    commission: float = 0.0
    slippage: float = 0.0
    strategy: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def order_value(self) -> float:
        return self.price * self.quantity

    @property
    def fill_value(self) -> float:
        return self.fill_price * self.quantity


# ---------------------------------------------------------------------------
# PaperPosition
# ---------------------------------------------------------------------------


@dataclass
class PaperPosition:
    """An open position in paper trading."""

    symbol: str
    side: PositionSide
    entry_price: float
    quantity: int
    entry_time: datetime
    current_price: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy: str = ""

    @property
    def unrealized_pnl(self) -> float:
        if self.side == PositionSide.LONG:
            return (self.current_price - self.entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            return (self.entry_price - self.current_price) * self.quantity
        return 0.0

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        if self.side == PositionSide.LONG:
            return ((self.current_price / self.entry_price) - 1) * 100
        elif self.side == PositionSide.SHORT:
            return ((self.entry_price / self.current_price) - 1) * 100
        return 0.0

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    def update_price(self, price: float) -> None:
        self.current_price = price

    def to_domain_position(self) -> Any:
        """Convert to canonical ``domain.entities.Position`` (REF-016).

        Price fields are coerced to ``Decimal``.
        """
        from domain.entities import Position

        qty = self.quantity if self.side == PositionSide.LONG else -self.quantity
        return Position(
            symbol=self.symbol,
            exchange="NSE",
            quantity=qty,
            avg_price=Decimal(str(self.entry_price)),
            ltp=Decimal(str(self.current_price)),
        )


# ---------------------------------------------------------------------------
# PaperTrade
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperTrade:
    """A completed trade in paper trading."""

    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    quantity: int
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    commission: float
    slippage_cost: float
    strategy: str
    reasons: list[str] = field(default_factory=list)

    def to_domain_trade(self) -> Any:
        """Convert to canonical ``domain.entities.Trade`` (REF-016).

        Price and PnL fields are coerced to ``Decimal``.
        """
        from domain.entities import Trade
        from domain.types import Side

        side = Side.BUY if self.side == OrderSide.BUY else Side.SELL
        return Trade(
            trade_id=f"paper:{self.symbol}:{id(self)}",
            order_id="",
            symbol=self.symbol,
            exchange="NSE",
            side=side,
            quantity=self.quantity,
            price=Decimal(str(self.exit_price)),
            trade_value=Decimal(str(abs(self.pnl))) if self.pnl != 0 else Decimal("0"),
        )


# ---------------------------------------------------------------------------
# PaperSession
# ---------------------------------------------------------------------------


@dataclass
class PaperSession:
    """Tracks state during a paper trading session."""

    capital: float
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    trades: list[PaperTrade] = field(default_factory=list)
    orders: list[PaperOrder] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    bar_count: int = 0
    peak_equity: float = 0.0
    daily_pnl: float = 0.0
    daily_bars: int = 0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def open_positions(self) -> list[PaperPosition]:
        return list(self.positions.values())

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def total_equity(self) -> float:
        pos_value = sum(p.unrealized_pnl for p in self.positions.values())
        return self.capital + pos_value

    @property
    def total_invested(self) -> float:
        return sum(p.notional for p in self.positions.values())

    @property
    def available_capital(self) -> float:
        return self.capital

    @property
    def total_pnl(self) -> float:
        realized = sum(t.pnl for t in self.trades)
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        return realized + unrealized

    @property
    def total_realized_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def total_commission(self) -> float:
        return sum(t.commission for t in self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = 0.0
        max_dd = 0.0
        for _, eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def reset_daily(self) -> None:
        self.daily_pnl = 0.0
        self.daily_bars = 0


# ---------------------------------------------------------------------------
# PaperResult
# ---------------------------------------------------------------------------


@dataclass
class PaperResult:
    """Final output from a paper trading session."""

    session: PaperSession = field(default_factory=lambda: PaperSession(capital=0.0))
    config: PaperConfig = field(default_factory=PaperConfig)
    bars_processed: int = 0
    signals_generated: int = 0

    @property
    def final_equity(self) -> float:
        return self.session.total_equity

    @property
    def total_return_pct(self) -> float:
        initial = self.config.initial_capital
        if initial <= 0:
            return 0.0
        return ((self.final_equity / initial) - 1) * 100

    @property
    def sharpe_ratio(self) -> float:
        if len(self.session.equity_curve) < 2:
            return 0.0
        equities = [eq for _, eq in self.session.equity_curve]
        returns = [(equities[i] / equities[i - 1] - 1) for i in range(1, len(equities))]
        if not returns:
            return 0.0
        import numpy as np

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns))
        if std_ret == 0:
            return 0.0
        return round(mean_ret / std_ret * (252**0.5), 2)

    @property
    def summary(self) -> dict[str, object]:
        return {
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "total_trades": self.session.trades.__len__(),
            "open_positions": self.session.position_count,
            "win_rate": round(self.session.win_rate * 100, 1),
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "total_pnl": round(self.session.total_pnl, 2),
            "realized_pnl": round(self.session.total_realized_pnl, 2),
            "unrealized_pnl": round(self.session.total_unrealized_pnl, 2),
            "commission": round(self.session.total_commission, 2),
            "max_drawdown_pct": round(self.session.max_drawdown * 100, 2),
            "sharpe_ratio": self.sharpe_ratio,
            "available_capital": round(self.session.available_capital, 2),
        }
