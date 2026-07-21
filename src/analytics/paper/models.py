"""Paper Trading models — PaperConfig, PaperSession, PaperOrder, PaperPosition, PaperTrade, PaperResult.

Paper Trading runs the same FeaturePipeline + StrategyPipeline as live/replay/backtest,
but simulates order execution with realistic fills (slippage, commission).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from analytics.simulation.models import FillModel
from domain.constants import DEFAULT_EXCHANGE
from domain.entities import Trade
from domain.enums import OrderStatus, PositionSide, Side
from domain.portfolio_projection import PortfolioProjector
from domain.ports.time_service import get_current_clock
from domain.simulation_fill_pipeline import SimulationFillPipeline
from domain.simulation_position_meta import PositionMeta
from domain.trading_costs import CommissionModel, IndianMarketFees

# Back-compat alias: older call sites and tests refer to Side as OrderSide.
OrderSide = Side

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
        Simulated slippage as % of price (applied once in OmsBacktestAdapter).
    commission_pct:
        Legacy field — unused on OMS paths. Prefer ``commission_model`` +
        ``commission_flat`` (same as ReplayConfig).
    commission_flat:
        Flat commission per trade when ``commission_model`` is FLAT.
    commission_model:
        How to calculate commissions (delegates to domain.trading_costs).
    fill_model:
        CURRENT_CLOSE fills at bar close; NEXT_OPEN (default) fills at next open
        — same semantics as ReplayConfig.
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
    commission_model: CommissionModel = CommissionModel.FLAT
    indian_market_fees: IndianMarketFees = field(default_factory=IndianMarketFees)
    fill_model: FillModel = FillModel.NEXT_OPEN
    warmup_bars: int = 20
    window_size: int = 100
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 0.0
    max_daily_loss_pct: float = 0.0
    fail_closed_features: bool = True


# ---------------------------------------------------------------------------
# PaperOrder
# ---------------------------------------------------------------------------


@dataclass
class PaperOrder:
    """A simulated order in paper trading."""

    order_id: str
    symbol: str
    side: Side
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
    def market_value(self) -> float:
        """Mark-to-market position value (qty × latest price)."""
        px = self.current_price if self.current_price > 0 else self.entry_price
        return px * self.quantity

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
            exchange=DEFAULT_EXCHANGE,
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
    side: Side
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
        """Convert to canonical ``domain.entities.Trade`` via shared helper.

        ponytail: PaperTrade stays a thin session record; domain Trade is SSOT.
        The conversion lives in ``analytics.simulation.trade_mapping`` so
        replay and paper share one mapping.
        """
        from analytics.simulation.trade_mapping import sim_trade_to_domain

        return sim_trade_to_domain(
            trade_id=f"paper:{self.symbol}:{id(self)}",
            symbol=self.symbol,
            side=self.side,
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
    fill_pipeline: SimulationFillPipeline = field(default_factory=SimulationFillPipeline)
    position_meta: dict[str, PositionMeta] = field(default_factory=dict)
    trades: list[PaperTrade] = field(default_factory=list)
    orders: list[PaperOrder] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    bar_count: int = 0
    peak_equity: float = 0.0
    daily_pnl: float = 0.0
    daily_bars: int = 0

    @property
    def projector(self) -> PortfolioProjector:
        return self.fill_pipeline.projector

    def has_position(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> bool:
        pos = self.fill_pipeline.projector.get_position(symbol, exchange)
        return pos is not None and pos.quantity != 0

    def open_symbols(self) -> list[str]:
        return [p.symbol for p in self.fill_pipeline.projector.get_positions() if p.quantity != 0]

    def mark_symbol(self, symbol: str, price: float, exchange: str = DEFAULT_EXCHANGE) -> None:
        self.fill_pipeline.projector.mark_ltp(symbol, exchange, Decimal(str(price)))

    def bootstrap_position(
        self,
        position: PaperPosition,
        *,
        exchange: str = DEFAULT_EXCHANGE,
    ) -> None:
        """Seed projector + meta (tests / recovery)."""
        side = Side.BUY if position.side == PositionSide.LONG else Side.SELL
        order_id = f"bootstrap:{position.symbol}"
        trade = Trade(
            trade_id=f"{order_id}:{position.quantity}",
            order_id=order_id,
            symbol=position.symbol,
            exchange=exchange,
            side=side,
            quantity=position.quantity,
            price=Decimal(str(position.entry_price)),
            trade_value=Decimal(str(position.entry_price)) * position.quantity,
            timestamp=position.entry_time,
        )
        self.fill_pipeline.apply_trade(trade, order_quantity=position.quantity)
        mark = position.current_price if position.current_price > 0 else position.entry_price
        self.fill_pipeline.projector.mark_ltp(position.symbol, exchange, Decimal(str(mark)))
        self.position_meta[position.symbol] = PositionMeta(
            entry_time=position.entry_time,
            stop_loss=position.stop_loss,
            target=position.take_profit,
            strategy=position.strategy,
        )

    def clear_position(self, symbol: str) -> None:
        self.position_meta.pop(symbol, None)

    def _domain_position(self, symbol: str, exchange: str = DEFAULT_EXCHANGE):
        pos = self.fill_pipeline.projector.get_position(symbol, exchange)
        if pos is None or pos.quantity == 0:
            return None
        return pos

    def _to_paper_position(
        self, symbol: str, exchange: str = DEFAULT_EXCHANGE
    ) -> PaperPosition | None:
        pos = self._domain_position(symbol, exchange)
        if pos is None:
            return None
        meta = self.position_meta.get(symbol)
        side = PositionSide.LONG if pos.quantity > 0 else PositionSide.SHORT
        return PaperPosition(
            symbol=symbol,
            side=side,
            entry_price=float(pos.avg_price),
            quantity=abs(pos.quantity),
            entry_time=meta.entry_time if meta else get_current_clock().now(),
            current_price=float(pos.ltp),
            stop_loss=meta.stop_loss if meta else None,
            take_profit=meta.take_profit if meta else None,
            strategy=meta.strategy if meta else "",
        )

    @property
    def positions(self) -> dict[str, PaperPosition]:
        return {sym: view for sym in self.open_symbols() if (view := self._to_paper_position(sym))}

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def open_positions(self) -> list[PaperPosition]:
        return list(self.positions.values())

    @property
    def position_count(self) -> int:
        return len(self.open_symbols())

    @property
    def total_equity(self) -> float:
        pos_value = sum(
            float(p.ltp) * p.quantity
            for p in self.fill_pipeline.projector.get_positions()
            if p.quantity != 0
        )
        return self.capital + pos_value

    @property
    def total_invested(self) -> float:
        return sum(
            float(p.avg_price) * abs(p.quantity)
            for p in self.fill_pipeline.projector.get_positions()
            if p.quantity != 0
        )

    @property
    def available_capital(self) -> float:
        return self.capital

    @property
    def total_pnl(self) -> float:
        realized = sum(t.pnl for t in self.trades)
        unrealized = sum(
            float(p.unrealized_pnl)
            for p in self.fill_pipeline.projector.get_positions()
            if p.quantity != 0
        )
        return realized + unrealized

    @property
    def total_realized_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(
            float(p.unrealized_pnl)
            for p in self.fill_pipeline.projector.get_positions()
            if p.quantity != 0
        )

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
            "win_rate": round(float(self.session.win_rate) * 100, 1),
            "final_equity": round(float(self.final_equity), 2),
            "total_return_pct": round(float(self.total_return_pct), 2),
            "total_pnl": round(float(self.session.total_pnl), 2),
            "realized_pnl": round(float(self.session.total_realized_pnl), 2),
            "unrealized_pnl": round(float(self.session.total_unrealized_pnl), 2),
            "commission": round(float(self.session.total_commission), 2),
            "max_drawdown_pct": round(float(self.session.max_drawdown) * 100, 2),
            "sharpe_ratio": self.sharpe_ratio,
            "available_capital": round(float(self.session.available_capital), 2),
        }
