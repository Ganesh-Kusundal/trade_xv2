"""Replay Engine models — Bar, ReplayConfig, ReplaySession, ReplayResult.

The Replay Engine processes historical OHLCV data bar-by-bar through
the same FeaturePipeline + StrategyPipeline used in live trading.
This ensures parity: if a strategy works in replay, it works in live.

Usage:
    engine = ReplayEngine(pipeline, strategy_pipeline, config)
    result = engine.run(historical_data)
    for signal in result.signals:
        print(signal.symbol, signal.signal_type, signal.confidence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from domain.events.types import DomainEvent

from analytics.strategy.models import Signal
from domain.portfolio_projection import PortfolioProjector
from domain.simulation_fill_pipeline import SimulationFillPipeline
from domain.simulation_position_meta import PositionMeta
from domain.ports.time_service import get_current_clock

# ---------------------------------------------------------------------------
# ReplayItem — single item in the merged replay stream
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayItem:
    """A single item in the merged replay stream.

    Either a bar (with OHLCV data) or an event (a DomainEvent from
    the event log).  Items are sorted by (timestamp, seq) to produce
    a deterministic total order.
    """

    timestamp: datetime
    sequence: int
    kind: str  # "bar" or "event"
    symbol: str | None = None
    event: DomainEvent | None = None
    bar_data: dict[str, Any] | None = None  # OHLCV data

    def __lt__(self, other: ReplayItem) -> bool:
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        return self.sequence < other.sequence


@dataclass
class UnifiedReplayResult:
    """Output from a completed unified replay run."""

    replay_result: "ReplayResult | None"
    events_replayed: int
    bars_replayed: int
    state_matches: bool
    state_diff: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, Any]:
        s: dict[str, Any] = {
            "events_replayed": self.events_replayed,
            "bars_replayed": self.bars_replayed,
            "state_matches": self.state_matches,
        }
        if self.replay_result is not None:
            s.update(self.replay_result.summary)
        s.update(self.metadata)
        return s


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReplayMode(str, Enum):
    """How the replay engine processes bars."""

    BAR_BY_BAR = "bar_by_bar"  # Process every bar
    ON_CLOSE = "on_close"  # Only process close of each bar
    CUSTOM = "custom"  # User-defined filter


# Re-export canonical models from domain.trading_costs (single source of truth)
from domain.trading_costs import (
    CommissionModel,
    IndianMarketFees,
    SlippageModel,
)


class FillModel(str, Enum):
    """Fill price model for simulated trades."""

    CURRENT_CLOSE = "current_close"  # Fill at current bar's close (default, legacy)
    NEXT_OPEN = "next_open"  # Fill at next bar's open (more realistic)


# ---------------------------------------------------------------------------
# Indian Market Fees
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Domain bar SSOT — import HistoricalBar from domain.candles.historical
# ---------------------------------------------------------------------------

from domain.candles.historical import HistoricalBar  # noqa: F401 — re-exported via __init__


@dataclass
class ReplayConfig:
    """Configuration for a replay session.

    Parameters
    ----------
    initial_capital:
        Starting capital for the simulated portfolio.
    mode:
        How to process bars (bar_by_bar, on_close, custom).
    window_size:
        Number of bars to use as the feature computation window.
        If 0, uses all available bars from the start.
    warmup_bars:
        Number of bars to skip before generating signals (for indicator warmup).
    max_position_pct:
        Maximum % of capital to allocate to a single position.
    slippage_pct:
        Simulated slippage as a percentage of price. 0.01 means 0.01% slippage.
        Must be non-negative.
    slippage_model:
        How to calculate slippage. FIXED_PCT uses slippage_pct directly.
        VOLUME_WEIGHTED scales slippage inversely with volume.
    avg_volume:
        Average volume used as reference for VOLUME_WEIGHTED slippage model.
        Slippage = base_slippage * (avg_volume / bar_volume). If 0, uses
        a computed rolling average from available bars.
    commission_flat:
        Flat commission per trade (0.0 = no commission). Used when
        commission_model is FLAT.
    commission_model:
        How to calculate commissions. FLAT uses commission_flat.
        INDIAN_EQUITY and INDIAN_FNO use realistic Indian market fees.
    indian_market_fees:
        Fee structure for Indian market commission model. Only used when
        commission_model is INDIAN_EQUITY or INDIAN_FNO.
    segment:
        Market segment: "EQUITY" or "FNO". Determines which fee
        calculation is used for Indian market models.
    fill_model:
        How fill prices are determined. CURRENT_CLOSE fills at the current
        bar's close (default, legacy behavior). NEXT_OPEN fills at the next
        bar's open, which is more realistic for strategies that generate
        signals at bar close.
    publish_events:
        Whether to publish signals to the EventBus.
    """

    initial_capital: float = 100_000.0
    mode: ReplayMode = ReplayMode.BAR_BY_BAR
    window_size: int = 0  # 0 = use all bars from start
    warmup_bars: int = 0  # Skip first N bars for indicator warmup
    max_position_pct: float = 100.0  # Max % per position
    slippage_pct: float = 0.0
    slippage_model: SlippageModel = SlippageModel.FIXED_PCT
    avg_volume: float = 0.0  # Reference volume for VOLUME_WEIGHTED model
    commission_flat: float = 0.0
    commission_model: CommissionModel = CommissionModel.FLAT
    indian_market_fees: IndianMarketFees = field(default_factory=IndianMarketFees)
    segment: str = "EQUITY"  # "EQUITY" or "FNO"
    fill_model: FillModel = FillModel.NEXT_OPEN
    publish_events: bool = False
    fail_closed_features: bool = True

    def __post_init__(self) -> None:
        if self.slippage_pct < 0:
            raise ValueError("slippage_pct must be non-negative")
        if self.max_position_pct <= 0:
            raise ValueError("max_position_pct must be positive")
        if self.warmup_bars < 0:
            raise ValueError("warmup_bars must be non-negative")
        if self.commission_flat < 0:
            raise ValueError("commission_flat must be non-negative")


# ---------------------------------------------------------------------------
# Trade (simulated)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulatedTrade:
    """A simulated trade executed during replay.

    Named ``SimulatedTrade`` to avoid collision with the canonical
    ``Trade`` dataclass in :mod:`brokers.common.core.domain`.
    """

    symbol: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    exit_price: float | None = None
    quantity: int = 0
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    pnl: Decimal = Decimal("0")
    pnl_pct: float = 0.0
    strategy: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_domain_trade(self) -> Any:
        """Convert to canonical ``domain.entities.Trade`` via shared helper.

        ponytail: SimulatedTrade stays a thin session record; domain Trade is SSOT.
        The conversion itself lives in ``analytics.shared.trade_types`` so
        replay and paper share one mapping.
        """
        from analytics.shared.trade_types import sim_trade_to_domain

        return sim_trade_to_domain(
            trade_id=f"sim:{self.symbol}:{id(self)}",
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            price=Decimal(str(self.entry_price)),
            trade_value=Decimal(str(abs(self.pnl))) if self.pnl != 0 else Decimal("0"),
        )


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


@dataclass
class SimulatedPosition:
    """An open position during replay.

    Named ``SimulatedPosition`` to avoid collision with the canonical
    ``Position`` dataclass in :mod:`brokers.common.core.domain`.
    """

    symbol: str
    side: str
    entry_price: float
    quantity: int
    entry_time: datetime
    stop_loss: float | None = None
    target: float | None = None
    strategy: str = ""
    mark_price: float | None = None  # latest bar close for MTM equity

    @property
    def notional(self) -> float:
        return self.entry_price * self.quantity

    @property
    def market_value(self) -> float:
        """Mark-to-market position value (qty × latest close)."""
        px = self.mark_price if self.mark_price is not None else self.entry_price
        return px * self.quantity

    def to_domain_position(self) -> Any:
        """Convert to canonical ``domain.entities.Position`` (REF-016).

        Price fields are coerced to ``Decimal``.
        """
        from domain.entities import Position

        return Position(
            symbol=self.symbol,
            exchange="NSE",
            quantity=self.quantity if self.side == "BUY" else -self.quantity,
            avg_price=Decimal(str(self.entry_price)),
            ltp=Decimal(str(self.entry_price)),
        )


# ---------------------------------------------------------------------------
# ReplaySession
# ---------------------------------------------------------------------------


@dataclass
class ReplaySession:
    """Tracks state during a replay run.

    Updated bar-by-bar by the ReplayEngine.
    """

    capital: float = 0.0
    fill_pipeline: SimulationFillPipeline = field(default_factory=SimulationFillPipeline)
    position_meta: dict[str, PositionMeta] = field(default_factory=dict)
    trades: list[SimulatedTrade] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    bar_count: int = 0
    peak_equity: float = 0.0

    @property
    def projector(self) -> PortfolioProjector:
        return self.fill_pipeline.projector

    def has_position(self, symbol: str, exchange: str = "NSE") -> bool:
        pos = self.fill_pipeline.projector.get_position(symbol, exchange)
        return pos is not None and pos.quantity != 0

    def open_symbols(self) -> list[str]:
        return [
            p.symbol
            for p in self.fill_pipeline.projector.get_positions()
            if p.quantity != 0
        ]

    def mark_symbol(self, symbol: str, price: float, exchange: str = "NSE") -> None:
        from decimal import Decimal

        self.fill_pipeline.projector.mark_ltp(symbol, exchange, Decimal(str(price)))

    def bootstrap_position(
        self,
        position: SimulatedPosition,
        *,
        exchange: str = "NSE",
    ) -> None:
        from domain import Side as DomainSide
        from domain.entities import Trade
        from decimal import Decimal

        side = DomainSide.BUY if position.side == "BUY" else DomainSide.SELL
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
        mark = position.mark_price if position.mark_price is not None else position.entry_price
        self.fill_pipeline.projector.mark_ltp(position.symbol, exchange, Decimal(str(mark)))
        self.position_meta[position.symbol] = PositionMeta(
            entry_time=position.entry_time,
            stop_loss=position.stop_loss,
            target=position.target,
            strategy=position.strategy,
        )

    def clear_position(self, symbol: str) -> None:
        self.position_meta.pop(symbol, None)

    def _to_simulated_position(self, symbol: str, exchange: str = "NSE") -> SimulatedPosition | None:
        pos = self.fill_pipeline.projector.get_position(symbol, exchange)
        if pos is None or pos.quantity == 0:
            return None
        meta = self.position_meta.get(symbol)
        return SimulatedPosition(
            symbol=symbol,
            side="BUY" if pos.quantity > 0 else "SELL",
            entry_price=float(pos.avg_price),
            quantity=abs(pos.quantity),
            entry_time=meta.entry_time if meta else get_current_clock().now(),
            stop_loss=meta.stop_loss if meta else None,
            target=meta.target if meta else None,
            strategy=meta.strategy if meta else "",
            mark_price=float(pos.ltp),
        )

    @property
    def positions(self) -> dict[str, SimulatedPosition]:
        return {
            sym: view for sym in self.open_symbols() if (view := self._to_simulated_position(sym))
        }

    @property
    def position(self) -> SimulatedPosition | None:
        """Backward-compat accessor for single-symbol replay paths."""
        symbols = self.open_symbols()
        if not symbols:
            return None
        return self._to_simulated_position(symbols[0])

    @position.setter
    def position(self, value: SimulatedPosition | None) -> None:
        """Backward-compat setter for single-symbol replay paths."""
        if value is None:
            self.position_meta.clear()
        else:
            self.bootstrap_position(value)

    @property
    def current_equity(self) -> float:
        """Current total equity (cash + mark-to-market position values)."""
        pos_value = sum(
            float(p.ltp) * p.quantity
            for p in self.fill_pipeline.projector.get_positions()
            if p.quantity != 0
        )
        return self.capital + pos_value

    @property
    def total_pnl(self) -> float:
        return self.current_equity - self.equity_curve[0][1] if self.equity_curve else 0.0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

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


# ---------------------------------------------------------------------------
# ReplayResult
# ---------------------------------------------------------------------------


@dataclass
class ReplayResult:
    """Final output from a completed replay session."""

    session: ReplaySession = field(default_factory=ReplaySession)
    config: ReplayConfig = field(default_factory=ReplayConfig)
    bars_processed: int = 0
    signals_generated: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def final_equity(self) -> float:
        return self.session.current_equity

    @property
    def total_return_pct(self) -> float:
        if not self.session.equity_curve:
            return 0.0
        initial = self.session.equity_curve[0][1]
        final = self.session.current_equity
        return ((final / initial) - 1) * 100 if initial > 0 else 0.0

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio from equity curve returns."""
        if len(self.session.equity_curve) < 2:
            return 0.0
        equities = [float(eq) for _, eq in self.session.equity_curve]
        returns = [(equities[i] / equities[i - 1] - 1) for i in range(1, len(equities))]
        if not returns:
            return 0.0
        import numpy as np

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns))
        if std_ret == 0:
            return 0.0
        return round(mean_ret / std_ret * (252**0.5), 2)  # Annualized

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "total_trades": self.session.total_trades,
            "win_rate": round(self.session.win_rate * 100, 1),
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "max_drawdown_pct": round(self.session.max_drawdown * 100, 2),
            "sharpe_ratio": self.sharpe_ratio,
        }
