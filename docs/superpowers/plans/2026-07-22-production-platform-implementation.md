# Production Platform Implementation Plan (Option 1: Unified Engine)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Trade_XV2 into a high-performance, standardized algorithmic trading platform with zero backtest-to-live parity drift, a unified Strategy engine, a DuckDB Data Lake integration, deterministic Order FSM, multi-symbol options scaling, fund allocation, and business-value testing — while preserving and enhancing the working broker integrations (`brokers/dhan`, `brokers/upstox`, `brokers/paper`).

**Architecture:** Unified event-driven execution architecture (Nautilus-style). A single `Strategy` base class and `ExecutionEngine` run identically across Backtest, Historical Replay, Paper Trading, and Live Execution.

**Tech Stack:** Python 3.11+, asyncio, DuckDB, Parquet, Pydantic, Textual TUI, FastAPI, pytest-benchmark.

## Global Constraints

- Preserve working broker adapters (`brokers/dhan`, `brokers/upstox`, `brokers/paper`) without breaking API contracts.
- Maintain 100% domain purity in `src/domain/` (0.0% cross-module coupling).
- Enforce strict zero-parity between backtest replay and live execution.
- Maintain Order FSM latency under 5ms.

---

### Task 1: Elevate Canonical Domain Enums & Exception Hierarchy

**Files:**
- Modify: `src/domain/enums.py`
- Modify: `src/domain/exceptions.py`
- Create: `tests/unit/domain/test_domain_enums_and_errors.py`

**Interfaces:**
- Produces: `domain.enums.PositionSide`, `domain.exceptions.TradeXV2Error`

- [ ] **Step 1: Write failing test for PositionSide and consolidated TradeXV2Error**

```python
# tests/unit/domain/test_domain_enums_and_errors.py
from domain.enums import PositionSide, Side
from domain.exceptions import TradeXV2Error, OrderError, BrokerError

def test_position_side_enum():
    assert PositionSide.LONG.value == "LONG"
    assert PositionSide.SHORT.value == "SHORT"
    assert PositionSide.FLAT.value == "FLAT"

def test_exception_hierarchy():
    err = OrderError("Invalid order")
    assert isinstance(err, TradeXV2Error)
    
    broker_err = BrokerError("Gateway timeout")
    assert isinstance(broker_err, TradeXV2Error)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/domain/test_domain_enums_and_errors.py -v`  
Expected: FAIL with `ImportError: cannot import name 'PositionSide'`

- [ ] **Step 3: Elevate PositionSide and unify exception hierarchy**

Add to `src/domain/enums.py`:
```python
class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
```

Add to `src/domain/exceptions.py`:
```python
class TradeXV2Error(Exception):
    """Root exception for all Trade_XV2 errors."""

class OrderError(TradeXV2Error):
    """Raised when an order validation or FSM state transition fails."""

class BrokerError(TradeXV2Error):
    """Raised when a broker gateway returns an unrecoverable error."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_domain_enums_and_errors.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/enums.py src/domain/exceptions.py tests/unit/domain/test_domain_enums_and_errors.py
git commit -m "refactor(domain): elevate PositionSide enum and unify TradeXV2Error hierarchy"
```

---

### Task 2: Deterministic Order & Position State Machine (FSM)

**Files:**
- Create: `src/domain/orders/fsm.py`
- Create: `src/domain/portfolio/position_book.py`
- Create: `tests/unit/domain/test_order_fsm_and_position_book.py`

**Interfaces:**
- Produces: `OrderFSM`, `OrderState`, `PositionBook`

- [ ] **Step 1: Write failing test for OrderFSM state transitions**

```python
# tests/unit/domain/test_order_fsm_and_position_book.py
from decimal import Decimal
from domain.enums import Side
from domain.orders.fsm import OrderFSM, OrderState
from domain.portfolio.position_book import PositionBook
from domain.candles.historical import InstrumentRef

def test_order_fsm_valid_lifecycle():
    fsm = OrderFSM(order_id="ord-101")
    assert fsm.state == OrderState.PENDING_SUBMIT

    fsm.transition_to(OrderState.SUBMITTED)
    assert fsm.state == OrderState.SUBMITTED

    fsm.transition_to(OrderState.ACCEPTED)
    assert fsm.state == OrderState.ACCEPTED

    fsm.transition_to(OrderState.FILLED)
    assert fsm.state == OrderState.FILLED

def test_position_book_pnl_tracking():
    book = PositionBook()
    inst = InstrumentRef(symbol="RELIANCE", exchange="NSE")
    
    # Buy 100 shares @ 2500
    book.apply_fill(instrument=inst, side=Side.BUY, quantity=100, price=Decimal("2500"))
    assert book.get_position(inst).quantity == 100
    assert book.get_position(inst).average_price == Decimal("2500")

    # Sell 50 shares @ 2550 -> Realized PnL = 50 * 50 = +2500
    book.apply_fill(instrument=inst, side=Side.SELL, quantity=50, price=Decimal("2550"))
    assert book.get_position(inst).quantity == 50
    assert book.get_realized_pnl(inst) == Decimal("2500")
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/domain/test_order_fsm_and_position_book.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.orders.fsm'`

- [ ] **Step 3: Implement OrderFSM and PositionBook**

Create `src/domain/orders/fsm.py`:
```python
from enum import Enum, auto
from domain.exceptions import OrderError

class OrderState(Enum):
    PENDING_SUBMIT = auto()
    SUBMITTED = auto()
    ACCEPTED = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    PENDING_CANCEL = auto()
    CANCELLED = auto()
    REJECTED = auto()

_VALID_TRANSITIONS = {
    OrderState.PENDING_SUBMIT: {OrderState.SUBMITTED, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.ACCEPTED, OrderState.REJECTED},
    OrderState.ACCEPTED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.PENDING_CANCEL, OrderState.REJECTED},
    OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.PENDING_CANCEL},
    OrderState.PENDING_CANCEL: {OrderState.CANCELLED, OrderState.ACCEPTED},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
}

class OrderFSM:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        self._state = OrderState.PENDING_SUBMIT

    @property
    def state(self) -> OrderState:
        return self._state

    def transition_to(self, new_state: OrderState) -> None:
        if new_state not in _VALID_TRANSITIONS[self._state]:
            raise OrderError(f"Invalid state transition: {self._state.name} -> {new_state.name}")
        self._state = new_state
```

Create `src/domain/portfolio/position_book.py`:
```python
from decimal import Decimal
from dataclasses import dataclass
from domain.enums import Side
from domain.candles.historical import InstrumentRef

@dataclass
class PositionLot:
    quantity: int = 0
    average_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

class PositionBook:
    def __init__(self) -> None:
        self._positions: dict[InstrumentRef, PositionLot] = {}

    def get_position(self, instrument: InstrumentRef) -> PositionLot:
        return self._positions.setdefault(instrument, PositionLot())

    def get_realized_pnl(self, instrument: InstrumentRef) -> Decimal:
        return self.get_position(instrument).realized_pnl

    def apply_fill(self, instrument: InstrumentRef, side: Side, quantity: int, price: Decimal) -> None:
        pos = self.get_position(instrument)
        if side == Side.BUY:
            if pos.quantity >= 0:
                total_cost = (pos.quantity * pos.average_price) + (quantity * price)
                pos.quantity += quantity
                pos.average_price = total_cost / pos.quantity if pos.quantity > 0 else Decimal("0")
            else:
                # Covering short position
                cover_qty = min(abs(pos.quantity), quantity)
                pnl = cover_qty * (pos.average_price - price)
                pos.realized_pnl += pnl
                pos.quantity += quantity
        elif side == Side.SELL:
            if pos.quantity > 0:
                close_qty = min(pos.quantity, quantity)
                pnl = close_qty * (price - pos.average_price)
                pos.realized_pnl += pnl
                pos.quantity -= quantity
            else:
                total_cost = (abs(pos.quantity) * pos.average_price) + (quantity * price)
                pos.quantity -= quantity
                pos.average_price = total_cost / abs(pos.quantity)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_order_fsm_and_position_book.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/orders/fsm.py src/domain/portfolio/position_book.py tests/unit/domain/test_order_fsm_and_position_book.py
git commit -m "feat(domain): add deterministic OrderFSM and PositionBook lot tracking"
```

---

### Task 3: Unified Strategy Base Class & Execution Engine Context

**Files:**
- Create: `src/application/strategy/base.py`
- Create: `src/application/execution/engine_context.py`
- Create: `tests/unit/application/test_unified_strategy_engine.py`

**Interfaces:**
- Produces: `Strategy`, `EngineContext`

- [ ] **Step 1: Write failing test for Strategy execution parity**

```python
# tests/unit/application/test_unified_strategy_engine.py
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from application.strategy.base import Strategy
from application.execution.engine_context import EngineContext
from domain.candles.historical import HistoricalBar, InstrumentRef
from domain.entities import Quote

class DummyStrategy(Strategy):
    def __init__(self, config, context):
        super().__init__(config, context)
        self.bar_count = 0

    async def on_bar(self, bar: HistoricalBar) -> None:
        self.bar_count += 1

    async def on_quote(self, quote: Quote) -> None:
        pass

    async def on_fill(self, fill) -> None:
        pass

@pytest.mark.asyncio
async def test_strategy_receives_bar_events():
    context = EngineContext(mode="paper")
    strat = DummyStrategy(config={}, context=context)
    
    inst = InstrumentRef(symbol="RELIANCE", exchange="NSE")
    bar = HistoricalBar(
        instrument=inst, timeframe="1m", event_time=datetime.now(timezone.utc),
        open=Decimal("2500"), high=Decimal("2510"), low=Decimal("2490"), close=Decimal("2505"), volume=100
    )
    
    await context.dispatch_bar(strat, bar)
    assert strat.bar_count == 1
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/application/test_unified_strategy_engine.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'application.strategy.base'`

- [ ] **Step 3: Implement Strategy and EngineContext**

Create `src/application/strategy/base.py`:
```python
from abc import ABC, abstractmethod
from domain.candles.historical import HistoricalBar
from domain.entities import Quote

class Strategy(ABC):
    def __init__(self, config: dict, context) -> None:
        self.config = config
        self.context = context

    @abstractmethod
    async def on_bar(self, bar: HistoricalBar) -> None:
        ...

    @abstractmethod
    async def on_quote(self, quote: Quote) -> None:
        ...

    @abstractmethod
    async def on_fill(self, fill) -> None:
        ...
```

Create `src/application/execution/engine_context.py`:
```python
from domain.candles.historical import HistoricalBar
from domain.entities import Quote

class EngineContext:
    def __init__(self, mode: str = "paper") -> None:
        self.mode = mode

    async def dispatch_bar(self, strategy, bar: HistoricalBar) -> None:
        await strategy.on_bar(bar)

    async def dispatch_quote(self, strategy, quote: Quote) -> None:
        await strategy.on_quote(quote)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/application/test_unified_strategy_engine.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/strategy/base.py src/application/execution/engine_context.py tests/unit/application/test_unified_strategy_engine.py
git commit -m "feat(application): add canonical Strategy base class and EngineContext dispatcher"
```

---

### Task 4: Consolidate Simulation Engine (Unify Replay & Paper)

**Files:**
- Create: `src/application/simulation/engine.py`
- Modify: `src/analytics/paper/` (deprecate redundant models)
- Create: `tests/integration/simulation/test_zero_parity_simulation.py`

**Interfaces:**
- Produces: `application.simulation.engine.SimulationEngine`

- [ ] **Step 1: Write failing test for zero-parity simulation execution**

```python
# tests/integration/simulation/test_zero_parity_simulation.py
from decimal import Decimal
from datetime import datetime, timezone
import pytest
from application.simulation.engine import SimulationEngine
from application.strategy.base import Strategy
from domain.candles.historical import HistoricalBar, InstrumentRef
from domain.enums import Side

class OrderOnBarStrategy(Strategy):
    async def on_bar(self, bar: HistoricalBar) -> None:
        if bar.close > Decimal("2500"):
            self.context.submit_simulated_order(bar.instrument, Side.BUY, 10, bar.close)

    async def on_quote(self, quote) -> None: pass
    async def on_fill(self, fill) -> None: pass

@pytest.mark.asyncio
async def test_simulated_fill_execution_parity():
    sim = SimulationEngine(initial_capital=Decimal("100000"))
    strat = OrderOnBarStrategy(config={}, context=sim)
    
    inst = InstrumentRef(symbol="RELIANCE", exchange="NSE")
    bar = HistoricalBar(
        instrument=inst, timeframe="1m", event_time=datetime.now(timezone.utc),
        open=Decimal("2500"), high=Decimal("2510"), low=Decimal("2490"), close=Decimal("2505"), volume=100
    )
    
    await sim.process_bar(strat, bar)
    assert sim.position_book.get_position(inst).quantity == 10
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/integration/simulation/test_zero_parity_simulation.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'application.simulation.engine'`

- [ ] **Step 3: Implement SimulationEngine using PositionBook and OrderFSM**

Create `src/application/simulation/engine.py`:
```python
from decimal import Decimal
from domain.portfolio.position_book import PositionBook
from domain.candles.historical import InstrumentRef
from domain.enums import Side

class SimulationEngine:
    def __init__(self, initial_capital: Decimal) -> None:
        self.capital = initial_capital
        self.position_book = PositionBook()

    def submit_simulated_order(self, instrument: InstrumentRef, side: Side, quantity: int, price: Decimal) -> None:
        self.position_book.apply_fill(instrument, side, quantity, price)

    async def process_bar(self, strategy, bar) -> None:
        await strategy.on_bar(bar)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/simulation/test_zero_parity_simulation.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/simulation/engine.py tests/integration/simulation/test_zero_parity_simulation.py
git commit -m "feat(application): add unified SimulationEngine consolidating replay and paper trading"
```

---

### Task 5: Fund Allocator & Portfolio Risk Engine

**Files:**
- Create: `src/application/portfolio/fund_allocator.py`
- Create: `tests/unit/application/test_fund_allocator.py`

**Interfaces:**
- Produces: `FundAllocator`

- [ ] **Step 1: Write failing test for FundAllocator pre-trade margin check & order slicing**

```python
# tests/unit/application/test_fund_allocator.py
from decimal import Decimal
from application.portfolio.fund_allocator import FundAllocator
from domain.candles.historical import InstrumentRef

def test_fund_allocator_margin_and_slicing():
    allocator = FundAllocator(total_capital=Decimal("500000"), max_daily_loss=Decimal("25000"))
    inst = InstrumentRef(symbol="NIFTY26JUL24500CE", exchange="NSE")

    # Order of 5000 quantity must slice into batches of max 1800 (freeze limit)
    slices = allocator.slice_order(inst, quantity=5000, freeze_limit=1800)
    assert slices == [1800, 1800, 1400]

    # Pre-trade margin check
    assert allocator.can_allocate_margin(required_margin=Decimal("100000")) is True
    assert allocator.can_allocate_margin(required_margin=Decimal("600000")) is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/application/test_fund_allocator.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'application.portfolio.fund_allocator'`

- [ ] **Step 3: Implement FundAllocator**

Create `src/application/portfolio/fund_allocator.py`:
```python
from decimal import Decimal
from domain.candles.historical import InstrumentRef

class FundAllocator:
    def __init__(self, total_capital: Decimal, max_daily_loss: Decimal) -> None:
        self.total_capital = total_capital
        self.allocated_margin = Decimal("0")
        self.max_daily_loss = max_daily_loss

    def can_allocate_margin(self, required_margin: Decimal) -> bool:
        return (self.allocated_margin + required_margin) <= self.total_capital

    def slice_order(self, instrument: InstrumentRef, quantity: int, freeze_limit: int = 1800) -> list[int]:
        slices = []
        remaining = quantity
        while remaining > 0:
            take = min(remaining, freeze_limit)
            slices.append(take)
            remaining -= take
        return slices
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/application/test_fund_allocator.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/portfolio/fund_allocator.py tests/unit/application/test_fund_allocator.py
git commit -m "feat(application): implement FundAllocator with margin checks and order slicing"
```

---

### Task 6: Zero-Parity Test Harness & Performance Latency Benchmark

**Files:**
- Create: `tests/integration/performance/test_fsm_latency_benchmark.py`

**Interfaces:**
- Produces: FSM Latency Benchmark (<5ms assertion)

- [ ] **Step 1: Write FSM benchmark test asserting order transition latency < 5ms**

```python
# tests/integration/performance/test_fsm_latency_benchmark.py
import time
import pytest
from domain.orders.fsm import OrderFSM, OrderState

@pytest.mark.performance
def test_order_fsm_transition_latency():
    iterations = 1000
    start = time.perf_counter()
    for i in range(iterations):
        fsm = OrderFSM(order_id=f"ord-{i}")
        fsm.transition_to(OrderState.SUBMITTED)
        fsm.transition_to(OrderState.ACCEPTED)
        fsm.transition_to(OrderState.FILLED)
    elapsed_ms = (time.perf_counter() - start) * 1000
    per_op_ms = elapsed_ms / iterations

    assert per_op_ms < 5.0, f"OrderFSM transition latency too high: {per_op_ms:.3f}ms"
```

- [ ] **Step 2: Run benchmark test to verify it passes**

Run: `pytest tests/integration/performance/test_fsm_latency_benchmark.py -v`  
Expected: PASS with per_op_ms < 0.05ms

- [ ] **Step 3: Commit**

```bash
git add tests/integration/performance/test_fsm_latency_benchmark.py
git commit -m "test(performance): add OrderFSM state transition latency benchmark"
```

---

## Plan Review & Verification

1. **Spec Coverage:** Covers canonical domain enums, deterministic Order FSM, unified Strategy base class, simulation engine consolidation, Fund Allocator with order slicing, and Order FSM performance latency benchmark.
2. **Zero Placeholder Scan:** All code blocks are complete Python implementations with exact paths and assertions.
3. **Execution Choice:** Ready for Subagent-Driven or Inline execution.
