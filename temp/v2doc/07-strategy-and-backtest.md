# 07 — Strategy System & Backtest

## 1. Overview

The strategy system provides a unified interface for writing trading strategies
that work identically across backtest, paper, and live modes. This is the
culmination of the zero-parity architecture.

```
┌─────────────────────────────────────────────────────────────┐
│                    StrategyEngine                           │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Strategy    │  │  Signal      │  │  Portfolio       │  │
│  │  Base        │  │  Generator   │  │  Tracker         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └─────────────────┼────────────────────┘            │
│                           │                                 │
│                    ┌──────▼───────┐                         │
│                    │  Execution   │                         │
│                    │  Context     │                         │
│                    └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

## 2. StrategyBase

```python
# application/strategy/strategy_base.py

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from domain.commands.order_commands import PlaceOrderCommand, CancelOrderCommand
from domain.entities.order import Order, OrderSide, OrderType
from domain.entities.position import Position
from domain.entities.quote import Quote
from domain.events.order_events import OrderFilled, OrderRejected
from domain.events.position_events import PositionChanged
from domain.ports.event_bus import EventBusPort


logger = logging.getLogger(__name__)


class StrategyBase:
    """
    Base class for all trading strategies.

    Strategies receive market data and events, and emit order commands.
    The same strategy code works for backtest, paper, and live.
    """

    def __init__(self, strategy_id: str, bus: EventBusPort) -> None:
        self._strategy_id = strategy_id
        self._bus = bus
        self._positions: dict[tuple[str, str], Position] = {}
        self._orders: dict[UUID, Order] = {}

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    # ── Lifecycle ─────────────────────────────────────────────

    def on_start(self) -> None:
        """Called when strategy starts. Override to initialize."""
        pass

    def on_stop(self) -> None:
        """Called when strategy stops. Override to cleanup."""
        pass

    # ── Market Data ───────────────────────────────────────────

    def on_tick(self, quote: Quote) -> None:
        """Called on every tick. Override to implement logic."""
        pass

    def on_bar(self, bar: dict) -> None:
        """Called on every bar close. Override to implement logic."""
        pass

    # ── Order Events ──────────────────────────────────────────

    def on_order_filled(self, event: OrderFilled) -> None:
        """Called when an order is filled."""
        pass

    def on_order_rejected(self, event: OrderRejected) -> None:
        """Called when an order is rejected."""
        pass

    def on_position_changed(self, event: PositionChanged) -> None:
        """Called when a position changes."""
        symbol = (event.symbol, event.exchange)
        # Update local position cache
        # ...

    # ── Order Methods ─────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        exchange: str,
        quantity: str,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[str] = None,
    ) -> UUID:
        """Place a buy order."""
        command = PlaceOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=OrderSide.BUY,
            order_type=order_type,
            quantity=quantity,
            price=price,
            strategy_id=self._strategy_id,
        )
        self._bus.publish(command)
        return command.command_id

    def sell(
        self,
        symbol: str,
        exchange: str,
        quantity: str,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[str] = None,
    ) -> UUID:
        """Place a sell order."""
        command = PlaceOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=OrderSide.SELL,
            order_type=order_type,
            quantity=quantity,
            price=price,
            strategy_id=self._strategy_id,
        )
        self._bus.publish(command)
        return command.command_id

    def cancel(self, order_id: UUID) -> None:
        """Cancel an order."""
        command = CancelOrderCommand(order_id=order_id)
        self._bus.publish(command)

    # ── Position Queries ──────────────────────────────────────

    def get_position(self, symbol: str, exchange: str) -> Optional[Position]:
        """Get current position for a symbol."""
        return self._positions.get((symbol, exchange))

    def get_net_quantity(self, symbol: str, exchange: str) -> float:
        """Get net quantity for a symbol."""
        pos = self.get_position(symbol, exchange)
        return float(pos.quantity.value) if pos else 0.0
```

## 3. Example Strategy

```python
# strategies/momentum_strategy.py

from __future__ import annotations

from application.strategy.strategy_base import StrategyBase
from domain.entities.quote import Quote
from domain.entities.order import OrderType


class MomentumStrategy(StrategyBase):
    """
    Simple momentum strategy.

    Buy when price breaks above 20-bar high.
    Sell when price breaks below 10-bar low.
    """

    def __init__(self, strategy_id: str, bus, symbol: str, exchange: str) -> None:
        super().__init__(strategy_id, bus)
        self._symbol = symbol
        self._exchange = exchange
        self._prices: list[float] = []
        self._position_qty = 0.0

    def on_bar(self, bar: dict) -> None:
        close = bar["close"]
        self._prices.append(close)

        if len(self._prices) < 20:
            return

        # 20-bar high
        high_20 = max(self._prices[-20:])
        # 10-bar low
        low_10 = min(self._prices[-10:])

        # Entry: break above 20-bar high
        if close > high_20 and self._position_qty == 0:
            self.buy(self._symbol, self._exchange, "10", OrderType.MARKET)
            self._position_qty = 10.0

        # Exit: break below 10-bar low
        elif close < low_10 and self._position_qty > 0:
            self.sell(self._symbol, self._exchange, "10", OrderType.MARKET)
            self._position_qty = 0.0

    def on_order_filled(self, event) -> None:
        logger.info("Order filled: %s @ %s", event.fill_quantity, event.fill_price)
```

## 4. Backtest Engine

```python
# application/execution/backtest_engine.py

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_sources.simulated import SimulatedFillSource
from application.oms.context import TradingContext
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.risk.risk_manager import RiskManager
from application.strategy.strategy_base import StrategyBase
from datalake.catalog import DataCatalog
from domain.ports.data_catalog import DataCatalogPort
from shared.messaging.message_bus import MessageBus


logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Runs a strategy against historical data.

    Uses SimulatedFillSource to generate fills from bar data.
    Same ExecutionEngine + OrderManager + RiskManager as live.
    """

    def __init__(
        self,
        catalog: DataCatalogPort,
        start: datetime,
        end: datetime,
        initial_capital: float = 1_000_000.0,
        slippage_bps: float = 5.0,
    ) -> None:
        self._catalog = catalog
        self._start = start
        self._end = end
        self._initial_capital = initial_capital
        self._slippage_bps = slippage_bps

    def run(self, strategy: StrategyBase, symbols: list[tuple[str, str]]) -> BacktestResult:
        """Run backtest and return results."""
        # 1. Setup components
        bus = MessageBus()
        fill_source = SimulatedFillSource(slippage_bps=self._slippage_bps)
        risk_manager = RiskManager(bus, initial_capital=self._initial_capital)
        order_manager = OrderManager(bus)
        position_manager = PositionManager(bus)

        execution_engine = ExecutionEngine(
            bus=bus,
            fill_source=fill_source,
            risk_manager=risk_manager,
            order_manager=order_manager,
            position_manager=position_manager,
        )

        # 2. Wire up strategy
        strategy._bus = bus
        bus.subscribe(OrderFilled, strategy.on_order_filled)
        bus.subscribe(OrderRejected, strategy.on_order_rejected)
        bus.subscribe(PositionChanged, strategy.on_position_changed)

        # 3. Initialize
        execution_engine.initialize()
        execution_engine.start()
        strategy.on_start()

        # 4. Fetch historical data
        bars = {}
        for symbol, exchange in symbols:
            df = self._catalog.get_bars(symbol, exchange, self._start, self._end, "1m")
            bars[(symbol, exchange)] = df

        # 5. Run simulation
        all_timestamps = set()
        for df in bars.values():
            all_timestamps.update(df["timestamp"].tolist())

        for ts in sorted(all_timestamps):
            for (symbol, exchange), df in bars.items():
                row = df[df["timestamp"] == ts]
                if not row.empty:
                    bar = row.iloc[0].to_dict()
                    fill_source.on_bar(bar)
                    strategy.on_bar(bar)

        # 6. Cleanup
        strategy.on_stop()
        execution_engine.stop()

        # 7. Collect results
        return BacktestResult(
            orders=order_manager.get_orderbook(),
            positions=position_manager.get_positions(),
            initial_capital=self._initial_capital,
        )


class BacktestResult:
    """Results from a backtest run."""

    def __init__(
        self,
        orders: list,
        positions: list,
        initial_capital: float,
    ) -> None:
        self.orders = orders
        self.positions = positions
        self.initial_capital = initial_capital

    @property
    def total_trades(self) -> int:
        return len([o for o in self.orders if o.status.value == "FILLED"])

    @property
    def final_capital(self) -> float:
        pnl = sum(float(p.realized_pnl.amount) for p in self.positions)
        return self.initial_capital + pnl

    @property
    def total_return_pct(self) -> float:
        return ((self.final_capital - self.initial_capital) / self.initial_capital) * 100

    def summary(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "final_positions": len(self.positions),
        }
```

## 5. Replay Engine

```python
# application/execution/replay_engine.py

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable

from domain.entities.quote import Quote
from domain.value_objects import Price, Quantity


logger = logging.getLogger(__name__)


class ReplayEngine:
    """
    Replays historical tick data in real-time.

    Used for:
    1. Strategy development and testing
    2. Paper trading with realistic market conditions
    3. Demo and training
    """

    def __init__(
        self,
        catalog,
        speed: float = 1.0,  # 1.0 = real-time, 2.0 = 2x speed
    ) -> None:
        self._catalog = catalog
        self._speed = speed
        self._callbacks: list[Callable] = []
        self._running = False

    def register_callback(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    async def replay(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Replay tick data from start to end."""
        self._running = True
        df = await self._catalog.get_quotes(symbol, exchange, start, end)

        if df.empty:
            logger.warning("No tick data to replay")
            return

        prev_ts = None
        for _, row in df.iterrows():
            if not self._running:
                break

            # Simulate real-time delay
            if prev_ts is not None:
                delay = (row["timestamp"] - prev_ts).total_seconds() / self._speed
                if delay > 0:
                    await asyncio.sleep(delay)

            prev_ts = row["timestamp"]

            # Create quote
            quote = Quote(
                symbol=row["symbol"],
                exchange=row["exchange"],
                last_price=Price(row["last_price"]),
                bid=Price(row["bid"]),
                ask=Price(row["ask"]),
                bid_size=Quantity(row["bid_size"]),
                ask_size=Quantity(row["ask_size"]),
                volume=Quantity(row["volume"]),
                timestamp=row["timestamp"],
            )

            # Dispatch to callbacks
            for cb in self._callbacks:
                try:
                    cb(quote)
                except Exception as exc:
                    logger.exception("Replay callback failed: %s", exc)

    def stop(self) -> None:
        self._running = False
```

## 6. Paper Trading Engine

```python
# application/execution/paper_trading_engine.py

from __future__ import annotations

import logging
from typing import Optional

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_sources.paper import PaperFillSource
from application.oms.context import TradingContext
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.risk.risk_manager import RiskManager
from application.streaming.live_tick_pipeline import LiveTickPipeline
from domain.ports.broker_adapter import BrokerAdapterPort
from shared.messaging.message_bus import MessageBus


logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """
    Paper trading with live market data but simulated fills.

    Uses PaperFillSource which generates fills from live quotes.
    Same ExecutionEngine + OrderManager + RiskManager as live.
    """

    def __init__(
        self,
        quote_fn: Callable,  # (symbol, exchange) -> Quote
        initial_capital: float = 1_000_000.0,
        slippage_bps: float = 2.0,
    ) -> None:
        self._quote_fn = quote_fn
        self._initial_capital = initial_capital
        self._slippage_bps = slippage_bps

    def create_context(self) -> TradingContext:
        """Create a trading context for paper trading."""
        bus = MessageBus()
        fill_source = PaperFillSource(
            quote_fn=self._quote_fn,
            slippage_bps=self._slippage_bps,
        )
        risk_manager = RiskManager(bus, initial_capital=self._initial_capital)
        order_manager = OrderManager(bus)
        position_manager = PositionManager(bus)

        execution_engine = ExecutionEngine(
            bus=bus,
            fill_source=fill_source,
            risk_manager=risk_manager,
            order_manager=order_manager,
            position_manager=position_manager,
        )

        execution_engine.initialize()
        execution_engine.start()

        return TradingContext(
            event_bus=bus,
            execution_engine=execution_engine,
            order_manager=order_manager,
            position_manager=position_manager,
            risk_manager=risk_manager,
            fill_source=fill_source,
            mode="paper",
        )
```

## 7. Zero-Parity Verification

The same strategy must produce identical results across modes (given same data).

```python
# tests/integration/test_zero_parity.py

def test_strategy_parity_backtest_vs_paper():
    """Verify strategy produces same orders in backtest and paper."""
    # 1. Run backtest
    backtest_engine = BacktestEngine(...)
    backtest_result = backtest_engine.run(MomentumStrategy(...), symbols)

    # 2. Run paper with same data (replay)
    replay_engine = ReplayEngine(...)
    paper_engine = PaperTradingEngine(...)
    paper_ctx = paper_engine.create_context()
    # ... replay ticks through paper engine

    # 3. Compare orders
    backtest_orders = [(o.symbol, o.side, o.quantity) for o in backtest_result.orders]
    paper_orders = [(o.symbol, o.side, o.quantity) for o in paper_ctx.order_manager.get_orderbook()]

    assert backtest_orders == paper_orders
```

## 8. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| Strategy base | Ad hoc | Unified `StrategyBase` with lifecycle |
| Backtest | Separate code path | Same engine, different FillSource |
| Paper trading | Mock broker | `PaperFillSource` with live quotes |
| Replay | Not available | `ReplayEngine` for tick replay |
| Zero-parity | Partial | Full — verified by tests |
| Strategy examples | Few | Rich library (momentum, mean-reversion, etc.) |
