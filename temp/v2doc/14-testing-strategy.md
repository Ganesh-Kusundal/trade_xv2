# 14 — Testing Strategy

## 1. Overview

TradeXV2 follows the **test pyramid** with heavy emphasis on unit tests,
supported by integration tests, and a thin layer of end-to-end tests.

```
                    ┌─────────┐
                   /  E2E      \         ~5%  (full system)
                  /─────────────\
                 / Integration   \       ~25% (component pairs)
                /─────────────────\
               /    Unit Tests     \     ~70% (isolated classes)
              /─────────────────────\
```

## 2. Test Categories

### 2.1 Unit Tests (~70%)

Test individual classes and functions in isolation. No I/O, no network, no database.

**Location:** `tests/unit/`

**Key areas:**
- Domain entities (Order, Position, Trade)
- Value objects (Price, Quantity, Money)
- Risk rules
- MessageBus dispatch
- FillSource logic
- SymbolResolver
- Component lifecycle state machine

```python
# tests/unit/domain/test_order.py

from domain.entities.order import Order, OrderSide, OrderType, OrderStatus
from domain.value_objects import Price, Quantity, Symbol, Exchange
from uuid import uuid4
from decimal import Decimal

def test_order_remaining_quantity():
    order = Order(
        order_id=uuid4(),
        symbol=Symbol("RELIANCE"),
        exchange=Exchange("NSE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(Decimal("100")),
        price=Price(Decimal("2500")),
        filled_quantity=Quantity(Decimal("30")),
    )
    assert order.remaining_quantity == Quantity(Decimal("70"))

def test_order_is_active():
    order = Order(
        order_id=uuid4(),
        symbol=Symbol("RELIANCE"),
        exchange=Exchange("NSE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(Decimal("100")),
        status=OrderStatus.OPEN,
    )
    assert order.is_active is True
    assert order.is_terminal is False

def test_order_is_terminal():
    order = Order(
        order_id=uuid4(),
        symbol=Symbol("RELIANCE"),
        exchange=Exchange("NSE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(Decimal("100")),
        status=OrderStatus.FILLED,
    )
    assert order.is_active is False
    assert order.is_terminal is True
```

```python
# tests/unit/test_message_bus.py

from shared.messaging.message_bus import MessageBus
from domain.events.order_events import OrderPlaced, OrderFilled

def test_sync_publish_delivers_to_all_handlers():
    bus = MessageBus()
    received = []
    bus.subscribe(OrderPlaced, lambda e: received.append(e))
    bus.subscribe(OrderPlaced, lambda e: received.append(e))

    bus.publish(OrderPlaced())

    assert len(received) == 2

def test_failed_handler_does_not_block_others():
    bus = MessageBus()
    received = []

    def bad_handler(e):
        raise ValueError("boom")

    bus.subscribe(OrderPlaced, bad_handler)
    bus.subscribe(OrderPlaced, lambda e: received.append(e))

    bus.publish(OrderPlaced())

    assert len(received) == 1
    assert bus.metrics.messages_failed == 1
    assert len(bus.dead_letters) == 1

def test_unsubscribe_stops_delivery():
    bus = MessageBus()
    received = []
    sub = bus.subscribe(OrderPlaced, lambda e: received.append(e))

    bus.publish(OrderPlaced())
    assert len(received) == 1

    sub.unsubscribe()
    bus.publish(OrderPlaced())
    assert len(received) == 1  # no new delivery
```

### 2.2 Integration Tests (~25%)

Test component interactions. May use in-memory databases, fake brokers.

**Location:** `tests/integration/`

**Key areas:**
- ExecutionEngine + RiskManager + OrderManager
- BrokerGateway + Connection + Adapters
- DataEngine + DataCatalog
- StrategyEngine + ExecutionEngine
- Zero-parity verification

```python
# tests/integration/test_execution_flow.py

from shared.messaging.message_bus import MessageBus
from application.execution.execution_engine import ExecutionEngine
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.risk.risk_manager import RiskManager, RiskConfig
from domain.commands.order_commands import PlaceOrderCommand
from domain.entities.order import OrderSide, OrderType
from domain.events.order_events import OrderPlaced, OrderRejected
from domain.value_objects import Price, Quantity
from decimal import Decimal
from uuid import uuid4

class MockFillSource:
    async def submit_order(self, command):
        return uuid4()
    async def cancel_order(self, order_id):
        return True
    async def modify_order(self, order_id, command):
        return True

class MockRiskManager:
    def __init__(self, allow_all=True):
        self._allow_all = allow_all
    def check_order(self, command):
        from application.risk.risk_manager import RiskCheckResult
        if self._allow_all:
            return RiskCheckResult(ok=True)
        return RiskCheckResult(ok=False, reason="Denied")

def test_order_passes_risk_and_gets_placed():
    bus = MessageBus()
    risk = MockRiskManager(allow_all=True)
    fill_source = MockFillSource()
    om = OrderManager(bus)
    pm = PositionManager(bus)
    engine = ExecutionEngine(bus, fill_source, risk, om, pm)
    engine.initialize()
    engine.start()

    events = []
    bus.subscribe(OrderPlaced, lambda e: events.append(e))

    engine._on_place_order(PlaceOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity="10",
    ))

    assert len(events) == 1
    assert events[0].symbol == "RELIANCE"

def test_order_rejected_by_risk():
    bus = MessageBus()
    risk = MockRiskManager(allow_all=False)
    fill_source = MockFillSource()
    engine = ExecutionEngine(bus, fill_source, risk, OrderManager(bus), PositionManager(bus))
    engine.initialize()
    engine.start()

    events = []
    bus.subscribe(OrderRejected, lambda e: events.append(e))

    engine._on_place_order(PlaceOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity="10",
    ))

    assert len(events) == 1
    assert "Denied" in events[0].reason
```

### 2.3 End-to-End Tests (~5%)

Test full system from CLI/API to broker. Uses fake broker, real database.

**Location:** `tests/e2e/`

**Key areas:**
- Full order placement flow
- Backtest execution
- Paper trading session
- Data sync pipeline

```python
# tests/e2e/test_full_order_flow.py

from runtime.bootstrap import bootstrap
from pathlib import Path

def test_full_order_flow_paper_mode():
    """Test complete order flow in paper mode."""
    # Bootstrap in paper mode
    app = bootstrap(Path("config/test-paper.yaml"))
    ctx = app["context"]
    strategy = app["strategy"]

    # Place order via strategy
    order_id = strategy.buy("RELIANCE", "NSE", "10")

    # Verify order was placed
    orders = ctx.order_manager.get_orderbook()
    assert len(orders) > 0

    # Verify position updated
    positions = ctx.position_manager.get_positions()
    # ... assertions

    # Cleanup
    app["lifecycle"].stop_all()
```

## 3. Test Fixtures

```python
# tests/conftest.py

import pytest
from decimal import Decimal
from uuid import uuid4

from domain.entities.order import Order, OrderSide, OrderType, OrderStatus
from domain.entities.position import Position
from domain.entities.trade import Trade
from domain.entities.quote import Quote
from domain.value_objects import Price, Quantity, Money, Symbol, Exchange
from shared.messaging.message_bus import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def sample_order():
    return Order(
        order_id=uuid4(),
        symbol=Symbol("RELIANCE"),
        exchange=Exchange("NSE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(Decimal("100")),
        price=Price(Decimal("2500")),
        status=OrderStatus.OPEN,
    )


@pytest.fixture
def sample_trade():
    return Trade(
        trade_id=uuid4(),
        order_id=uuid4(),
        symbol=Symbol("RELIANCE"),
        exchange=Exchange("NSE"),
        side="BUY",
        quantity=Quantity(Decimal("100")),
        fill_price=Price(Decimal("2500")),
        commission=Money(Decimal("20"), "INR"),
    )


@pytest.fixture
def sample_quote():
    return Quote(
        symbol=Symbol("RELIANCE"),
        exchange=Exchange("NSE"),
        last_price=Price(Decimal("2500")),
        bid=Price(Decimal("2499")),
        ask=Price(Decimal("2501")),
        bid_size=Quantity(Decimal("500")),
        ask_size=Quantity(Decimal("300")),
        volume=Quantity(Decimal("1000000")),
    )
```

## 4. Adapter Harness

For testing broker adapters without hitting real APIs:

```python
# tests/harness/broker_harness.py

from typing import Any
from brokers.common.base_transport import BaseTransport


class FakeTransport(BaseTransport):
    """Fake HTTP transport for testing."""

    def __init__(self) -> None:
        self._responses: dict[str, Any] = {}
        self._requests: list[dict] = []

    def set_response(self, path: str, response: Any) -> None:
        self._responses[path] = response

    async def get(self, path: str, params: dict = None) -> dict:
        self._requests.append({"method": "GET", "path": path, "params": params})
        return self._responses.get(path, {})

    async def post(self, path: str, json: dict = None) -> dict:
        self._requests.append({"method": "POST", "path": path, "json": json})
        return self._responses.get(path, {})

    async def put(self, path: str, json: dict = None) -> dict:
        self._requests.append({"method": "PUT", "path": path, "json": json})
        return self._responses.get(path, {})

    async def delete(self, path: str) -> dict:
        self._requests.append({"method": "DELETE", "path": path})
        return self._responses.get(path, {})

    @property
    def is_connected(self) -> bool:
        return True

    async def authenticate(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    @property
    def requests(self) -> list[dict]:
        return self._requests
```

```python
# tests/integration/brokers/test_dhan_orders.py

import pytest
from brokers.dhan.adapters.orders import DhanOrdersAdapter
from brokers.dhan.wire import DhanWireAdapter
from brokers.common.symbol_resolver import SymbolResolver
from brokers.dhan.config.instrument_ref import DhanInstrumentRef
from tests.harness.broker_harness import FakeTransport


@pytest.fixture
def transport():
    return FakeTransport()

@pytest.fixture
def resolver():
    r = SymbolResolver()
    r.add("RELIANCE", "NSE", DhanInstrumentRef(
        exchange_segment="NSE_EQ",
        security_id="2885",
    ))
    return r

@pytest.fixture
def orders_adapter(transport, resolver):
    wire = DhanWireAdapter()
    return DhanOrdersAdapter(transport, wire, resolver)


@pytest.mark.asyncio
async def test_place_order_maps_request_correctly(orders_adapter, transport):
    transport.set_response("/orders", {
        "order_id": "12345",
        "status": "OPEN",
        "transaction_type": "BUY",
        "quantity": 10,
    })

    order = await orders_adapter.place_order(PlaceOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity="10",
    ))

    # Verify request mapping
    req = transport.requests[-1]
    assert req["method"] == "POST"
    assert req["path"] == "/orders"
    assert req["json"]["security_id"] == "2885"
    assert req["json"]["exchange_segment"] == "NSE_EQ"

    # Verify response mapping
    assert order.broker_order_id == "12345"
    assert order.status == OrderStatus.OPEN
```

## 5. Parity Tests

Verify that backtest, paper, and live produce identical results:

```python
# tests/integration/test_zero_parity.py

from application.execution.backtest_engine import BacktestEngine
from application.execution.paper_trading_engine import PaperTradingEngine
from application.execution.replay_engine import ReplayEngine
from strategies.momentum_strategy import MomentumStrategy
from datalake.catalog import DataCatalog
from pathlib import Path
from datetime import datetime


def test_backtest_paper_parity():
    """Verify same strategy produces same orders in backtest and paper."""
    catalog = DataCatalog(Path("datalake"))

    # 1. Run backtest
    bt_engine = BacktestEngine(
        catalog=catalog,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 31),
    )
    bt_result = bt_engine.run(
        MomentumStrategy("test", None, "RELIANCE", "NSE"),
        symbols=[("RELIANCE", "NSE")],
    )

    # 2. Run paper with replay
    paper_engine = PaperTradingEngine(quote_fn=lambda s, e: None)
    paper_ctx = paper_engine.create_context()
    strategy = MomentumStrategy("test", paper_ctx.event_bus, "RELIANCE", "NSE")

    replay = ReplayEngine(catalog, speed=100.0)  # Fast replay
    replay.register_callback(strategy.on_tick)

    # 3. Compare order sequences
    bt_orders = [
        (o.symbol, o.side.value, str(o.quantity.value))
        for o in bt_result.orders
        if o.status.value == "FILLED"
    ]
    paper_orders = [
        (o.symbol, o.side.value, str(o.quantity.value))
        for o in paper_ctx.order_manager.get_orderbook()
        if o.status.value == "FILLED"
    ]

    assert bt_orders == paper_orders
```

## 6. Performance Tests

```python
# tests/performance/test_message_bus_perf.py

import time
from shared.messaging.message_bus import MessageBus
from domain.events.order_events import OrderPlaced


def test_message_bus_throughput():
    """MessageBus should handle > 1M messages/sec."""
    bus = MessageBus()
    count = 0

    def handler(e):
        nonlocal count
        count += 1

    bus.subscribe(OrderPlaced, handler)

    n = 100_000
    t0 = time.perf_counter()
    for _ in range(n):
        bus.publish(OrderPlaced())
    elapsed = time.perf_counter() - t0

    rate = n / elapsed
    assert rate > 100_000  # At least 100k msg/sec
    assert count == n
```

## 7. Test Organization

```
tests/
├── conftest.py                    # Shared fixtures
├── unit/
│   ├── domain/
│   │   ├── test_order.py
│   │   ├── test_position.py
│   │   ├── test_trade.py
│   │   └── test_value_objects.py
│   ├── application/
│   │   ├── test_risk_manager.py
│   │   ├── test_order_manager.py
│   │   └── test_position_manager.py
│   ├── infrastructure/
│   │   ├── test_symbol_resolver.py
│   │   └── test_wire_adapter.py
│   └── shared/
│       ├── test_message_bus.py
│       └── test_component.py
│
├── integration/
│   ├── test_execution_flow.py
│   ├── test_zero_parity.py
│   ├── brokers/
│   │   ├── test_dhan_orders.py
│   │   ├── test_dhan_market_data.py
│   │   ├── test_upstox_orders.py
│   │   └── test_paper_gateway.py
│   └── data/
│       ├── test_data_catalog.py
│       └── test_data_engine.py
│
├── e2e/
│   ├── test_full_order_flow.py
│   ├── test_backtest_session.py
│   └── test_paper_trading.py
│
├── performance/
│   ├── test_message_bus_perf.py
│   └── test_data_catalog_perf.py
│
└── harness/
    ├── broker_harness.py
    ├── data_harness.py
    └── fixtures.py
```

## 8. CI Integration

```yaml
# In .github/workflows/ci.yml

test:
  runs-on: ubuntu-latest
  steps:
    - name: Unit tests
      run: uv run pytest tests/unit -v --cov=src --cov-report=xml

    - name: Integration tests
      run: uv run pytest tests/integration -v

    - name: E2E tests
      run: uv run pytest tests/e2e -v

    - name: Performance tests
      run: uv run pytest tests/performance -v --benchmark-only

    - name: Coverage gate
      run: |
        coverage report --fail-under=80
```

## 9. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| Unit tests | Ad hoc | Comprehensive, > 80% coverage |
| Integration tests | Few | Component pair testing |
| E2E tests | None | Full flow testing |
| Performance tests | None | Throughput + latency benchmarks |
| Test fixtures | Scattered | Centralized in conftest.py |
| Broker testing | Hits real API | FakeTransport harness |
| Parity tests | None | Backtest vs paper verification |
| CI gating | Basic | Coverage + import-linter + all test tiers |
