# Pure Redesign Plan — Brokers Module + Provider Layer

## Principle

**No wrappers. No shims. No adapters on top of existing code.**

Every new module is written from scratch with clean interfaces.
Old code is deprecated and deleted phase by phase.
The system never runs both old and new paths simultaneously.

---

## Phase 0: Delete Existing (Clean Slate)

### Files to Delete

```
DELETE:
├── src/domain/aggregates/instrument.py      # Replace with new Instrument
├── src/domain/instruments/instrument.py     # Replace with new Instrument
├── src/domain/instruments/subscription.py   # Replace with new Subscription
├── src/domain/options/option_chain.py       # Replace with new OptionChain
├── src/domain/ports/protocols.py            # Replace with new Ports
├── src/domain/ports/provider_registry.py    # Replace with new Registry
├── src/domain/extensions/base.py            # Replace with new Extension
├── src/domain/extensions/registry.py        # Replace with new Registry
├── src/domain/factories/instrument_factory.py  # Replace with new Factory
├── brokers/dhan/adapter.py                  # Delete (move to providers/)
├── brokers/upstox/adapter.py                # Delete (move to providers/)
├── brokers/common/adapters/*.py             # Delete all adapters
├── brokers/common/factory.py                # Replace with new Factory
├── brokers/common/bootstrap.py              # Replace with new Bootstrap
└── brokers/common/infrastructure.py         # Replace with new Infrastructure
```

### Keep (Unchanged)

```
KEEP:
├── brokers/dhan/gateway.py                  # Raw gateway (internal)
├── brokers/dhan/http_client.py              # HTTP client (internal)
├── brokers/dhan/config.py                   # Configuration (internal)
├── brokers/common/auth/*.py                 # Auth (internal)
├── brokers/common/resilience/*.py           # Rate limiting, circuit breaker (internal)
├── brokers/common/broker_port.py            # Legacy port (deprecated)
├── domain/entities/*.py                     # Value objects (keep)
├── domain/enums.py                          # Enums (keep)
└── domain/errors.py                         # Errors (keep)
```

---

## Phase 1: New Ports (Pure Interfaces)

### File: `src/domain/ports/data_provider.py`

```python
"""Data Provider — pure interface. No implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from domain.entities.market import MarketDepth, QuoteSnapshot
    from domain.entities.options import FutureChain, OptionChain
    from domain.instruments.instrument_id import InstrumentId


class DataProvider(ABC):
    """Pure interface for market data access.
    
    Implementations live in providers/ directory.
    Domain code depends only on this interface.
    """
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None: ...
    
    @abstractmethod
    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame: ...
    
    @abstractmethod
    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None: ...
    
    @abstractmethod
    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain: ...
    
    @abstractmethod
    def get_future_chain(self, underlying: InstrumentId) -> FutureChain: ...
    
    @abstractmethod
    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle: ...
    
    @abstractmethod
    def unsubscribe(self, handle: SubscriptionHandle) -> None: ...
```

### File: `src/domain/ports/execution_provider.py`

```python
"""Execution Provider — pure interface. No implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities.order import Order, OrderResponse
    from domain.entities.position import Position, Holding
    from domain.entities.account import Balance
    from domain.orders.requests import OrderRequest, ModifyOrderRequest


class ExecutionProvider(ABC):
    """Pure interface for order execution.
    
    Implementations live in providers/ directory.
    Domain code depends only on this interface.
    """
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse: ...
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse: ...
    
    @abstractmethod
    def modify_order(self, request: ModifyOrderRequest) -> OrderResponse: ...
    
    @abstractmethod
    def get_order_book(self) -> list[Order]: ...
    
    @abstractmethod
    def get_positions(self) -> list[Position]: ...
    
    @abstractmethod
    def get_holdings(self) -> list[Holding]: ...
    
    @abstractmethod
    def get_funds(self) -> Balance: ...
```

### File: `src/domain/ports/subscription_handle.py`

```python
"""Subscription Handle — pure interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SubscriptionHandle(ABC):
    """Handle returned by DataProvider.subscribe()."""
    
    @property
    @abstractmethod
    def is_active(self) -> bool: ...
    
    @abstractmethod
    def unsubscribe(self) -> None: ...
```

---

## Phase 2: New Domain Objects (Pure, No Wrappers)

### File: `src/domain/instruments/instrument.py` (New)

```python
"""Instrument — pure domain object. No inheritance from old code."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.data_provider import DataProvider
from domain.ports.execution_provider import ExecutionProvider
from domain.ports.subscription_handle import SubscriptionHandle


@dataclass
class InstrumentState:
    """Immutable state snapshot."""
    quote: QuoteSnapshot | None = None
    depth: MarketDepth | None = None
    is_subscribed: bool = False
    last_tick: QuoteSnapshot | None = None
    error: str | None = None


class Instrument:
    """Pure domain object. No wrappers. No shims.
    
    Usage:
        nifty = Instrument(InstrumentId.index("NSE", "NIFTY"))
        nifty.ltp
        nifty.subscribe()
    """
    
    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        data_provider: DataProvider | None = None,
        execution_provider: ExecutionProvider | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._id = instrument_id
        self._provider = data_provider
        self._executor = execution_provider
        self._metadata = metadata or {}
        self._state = InstrumentState()
        self._subscription: SubscriptionHandle | None = None
        self._callbacks: dict[str, list[Callable]] = {
            "tick": [], "quote": [], "depth": [],
            "disconnect": [], "reconnect": [],
        }
    
    # ── Identity ──
    @property
    def id(self) -> InstrumentId: return self._id
    
    @property
    def symbol(self) -> str: return self._id.underlying
    
    @property
    def exchange(self) -> str: return self._id.exchange
    
    @property
    def asset_type(self) -> str: return self._id.asset_type
    
    @property
    def lot_size(self) -> int: return self._metadata.get("lot_size", 1)
    
    @property
    def tick_size(self) -> Decimal:
        raw = self._metadata.get("tick_size")
        return Decimal(str(raw)) if raw else Decimal("0.05")

    # ── Live State ──
    @property
    def quote(self) -> QuoteSnapshot | None: return self._state.quote
    
    @property
    def ltp(self) -> Decimal | None:
        q = self._state.quote
        return q.ltp if q else None
    
    @property
    def bid(self) -> Decimal | None:
        q = self._state.quote
        return q.bid if q else None
    
    @property
    def ask(self) -> Decimal | None:
        q = self._state.quote
        return q.ask if q else None
    
    @property
    def volume(self) -> int:
        q = self._state.quote
        return q.volume if q else 0
    
    @property
    def market_depth(self) -> MarketDepth | None: return self._state.depth
    
    @property
    def order_book(self) -> MarketDepth | None: return self._state.depth
    
    @property
    def is_live(self) -> bool: return self._state.is_subscribed
    
    @property
    def last_tick(self) -> QuoteSnapshot | None: return self._state.last_tick

    # ── Behaviors ──
    def refresh(self) -> QuoteSnapshot | None:
        if self._provider is None: return None
        quote = self._provider.get_quote(self._id)
        self._state = InstrumentState(quote=quote, depth=self._state.depth)
        return quote
    
    def history(self, *, timeframe="1D", days=120, start=None, end=None):
        if self._provider is None: return pd.DataFrame()
        return self._provider.get_history(
            self._id, timeframe=timeframe, lookback_days=days,
            from_date=start, to_date=end,
        )
    
    def depth(self): return self._provider.get_depth(self._id) if self._provider else None
    
    def spread(self):
        if self.bid and self.ask: return self.ask - self.bid
        return None
    
    def mid_price(self):
        if self.bid and self.ask: return (self.bid + self.ask) / 2
        return None

    # ── Live Data ──
    def subscribe(self, callback=None, *, depth=False):
        if self._provider is None: return None
        def _wrapped(iid, payload):
            self._state = InstrumentState(
                quote=payload if not hasattr(payload, 'bids') else self._state.quote,
                depth=payload if hasattr(payload, 'bids') else self._state.depth,
                is_subscribed=True,
                last_tick=payload if not hasattr(payload, 'bids') else self._state.last_tick,
            )
            for cb in self._callbacks["tick"]: cb(payload)
            if callback: callback(iid, payload)
        handle = self._provider.subscribe(self._id, _wrapped, depth=depth)
        self._subscription = handle
        return handle
    
    def unsubscribe(self):
        if self._subscription:
            self._subscription.unsubscribe()
            self._subscription = None
    
    def on_tick(self, cb): self._callbacks["tick"].append(cb)
    def on_quote(self, cb): self._callbacks["quote"].append(cb)
    def on_depth(self, cb): self._callbacks["depth"].append(cb)
    def on_disconnect(self, cb): self._callbacks["disconnect"].append(cb)
    def on_reconnect(self, cb): self._callbacks["reconnect"].append(cb)

    # ── Chains ──
    def option_chain(self, expiry=None):
        if self._provider is None: return OptionChain.empty()
        chain = self._provider.get_option_chain(self._id, expiry=expiry)
        from domain.options.option_chain import OptionChain as RichChain
        return RichChain(chain, provider=self._provider)
    
    def future_chain(self):
        if self._provider is None: return FutureChain.empty()
        return self._provider.get_future_chain(self._id)

    # ── Orders ──
    def buy(self, quantity, price=None, order_type="LIMIT", product_type="INTRADAY"):
        if self._executor is None: raise RuntimeError("No execution provider")
        from domain.orders.requests import OrderRequest
        return self._executor.place_order(OrderRequest(
            symbol=self.symbol, exchange=self.exchange,
            transaction_type="BUY", quantity=quantity,
            price=price or Decimal("0"), order_type=order_type,
            product_type=product_type,
        ))
    
    def sell(self, quantity, price=None, order_type="LIMIT", product_type="INTRADAY"):
        if self._executor is None: raise RuntimeError("No execution provider")
        from domain.orders.requests import OrderRequest
        return self._executor.place_order(OrderRequest(
            symbol=self.symbol, exchange=self.exchange,
            transaction_type="SELL", quantity=quantity,
            price=price or Decimal("0"), order_type=order_type,
            product_type=product_type,
        ))
    
    def market(self, quantity, side="BUY"):
        return self.buy(quantity, order_type="MARKET") if side=="BUY" else self.sell(quantity, order_type="MARKET")
    
    def limit(self, quantity, price, side="BUY"):
        return self.buy(quantity, price) if side=="BUY" else self.sell(quantity, price)
    
    def stop_loss(self, quantity, trigger_price, side="BUY"):
        if self._executor is None: raise RuntimeError("No execution provider")
        from domain.orders.requests import OrderRequest
        return self._executor.place_order(OrderRequest(
            symbol=self.symbol, exchange=self.exchange,
            transaction_type=side.upper(), quantity=quantity,
            price=Decimal("0"), trigger_price=trigger_price,
            order_type="STOP_LOSS_MARKET", product_type="INTRADAY",
        ))

    # ── Extensions ──
    @property
    def broker(self):
        if self._provider is None: return None
        broker_id = getattr(self._provider, "name", None)
        return self._extensions.get(broker_id) if broker_id else None
    
    @property
    def extensions(self): return list(self._extensions.values())
    def has_extension(self, name): return name in self._extensions
    def get_extension(self, name): return self._extensions.get(name)

    # ── Serialization ──
    def serialize(self): return {"symbol": self.symbol, "exchange": self.exchange, "asset_type": self.asset_type}
    def clone(self): return type(self)(self._id, data_provider=self._provider, execution_provider=self._executor, metadata=self._metadata.copy())
    def statistics(self): return self.serialize() | (self._state.quote.__dict__ if self._state.quote else {})
    def snapshot(self): return {"id": str(self._id), "state": self._state.__dict__}
    
    def __repr__(self): return f"{type(self).__name__}({self._id})"
    def __eq__(self, other): return isinstance(other, Instrument) and self._id == other._id
    def __hash__(self): return hash(self._id)


class Equity(Instrument):
    def __init__(self, symbol, exchange="NSE", **kw):
        super().__init__(InstrumentId.equity(exchange, symbol), **kw)


class Index(Instrument):
    def __init__(self, name, exchange="NSE", **kw):
        super().__init__(InstrumentId.index(exchange, name), **kw)


class Future(Instrument):
    def __init__(self, symbol, exchange="NFO", *, expiry, **kw):
        super().__init__(InstrumentId.future(exchange, symbol, expiry), **kw)
        self._expiry = expiry
    @property
    def expiry(self): return self._expiry
    def basis(self, spot=None): return None
    def cost_of_carry(self, rate=None): return None
    def rollover(self): return None
    def continuous(self): return pd.DataFrame()


class Option(Instrument):
    def __init__(self, instrument_id, *, strike, expiry, right, leg=None, **kw):
        super().__init__(instrument_id, **kw)
        self._strike = strike
        self._expiry = expiry
        self._right = right
        self._leg = leg
    @property
    def strike(self): return self._strike
    @property
    def expiry(self): return self._expiry
    @property
    def right(self): return self._right
    @property
    def is_call(self): return self._right == "CE"
    @property
    def greeks(self):
        from domain.options.greeks import Greeks
        leg_greeks = getattr(self._leg, "greeks", None)
        return Greeks.from_dict(leg_greeks) if leg_greeks else Greeks.zero()
    @property
    def iv(self): return getattr(self._leg, "iv", None)
    def black_scholes(self, spot, rate=None): return None
    def payoff(self, spot): return None
    def intrinsic_value(self, spot): return None
    def extrinsic_value(self, spot): return None
    def moneyness(self, spot): return "ATM"
    def implied_volatility(self, market_price): return None
    @classmethod
    def from_leg(cls, underlying, exchange, expiry, strike, right, leg, **kw):
        from datetime import datetime as _dt
        exp = expiry if isinstance(expiry, date) else _dt.strptime(str(expiry), "%Y-%m-%d").date() if expiry else None
        iid = InstrumentId.option(exchange, underlying, exp, strike, right)
        return cls(iid, strike=strike, expiry=exp, right=right, leg=leg, **kw)


class Equity(Instrument):
    """Equity('RELIANCE')"""
    def __init__(self, symbol, exchange='NSE', **kw):
        super().__init__(InstrumentId.equity(exchange, symbol), **kw)


class Index(Instrument):
    """Index('NIFTY')"""
    def __init__(self, name, exchange='NSE', **kw):
        super().__init__(InstrumentId.index(exchange, name), **kw)


class Future(Instrument):
    """Future('NIFTY', expiry=date(...))"""
    def __init__(self, symbol, exchange='NFO', *, expiry, **kw):
        super().__init__(InstrumentId.future(exchange, symbol, expiry), **kw)
        self._expiry = expiry
    @property
    def expiry(self): return self._expiry
    def basis(self, spot=None): return None
    def cost_of_carry(self, rate=None): return None
    def rollover(self): return None
    def continuous(self): return pd.DataFrame()


class Option(Instrument):
    """Option with strike, expiry, right, greeks, iv."""
    def __init__(self, instrument_id, *, strike, expiry, right, leg=None, **kw):
        super().__init__(instrument_id, **kw)
        self._strike = strike
        self._expiry = expiry
        self._right = right
        self._leg = leg
    @property
    def strike(self): return self._strike
    @property
    def expiry(self): return self._expiry
    @property
    def right(self): return self._right
    @property
    def is_call(self): return self._right == 'CE'
    @property
    def greeks(self):
        from domain.options.greeks import Greeks
        leg_greeks = getattr(self._leg, 'greeks', None)
        return Greeks.from_dict(leg_greeks) if leg_greeks else Greeks.zero()
    @property
    def iv(self): return getattr(self._leg, 'iv', None)
    def black_scholes(self, spot, rate=None): return None
    def payoff(self, spot): return None
    def intrinsic_value(self, spot): return None
    def extrinsic_value(self, spot): return None
    def moneyness(self, spot): return 'ATM'
    def implied_volatility(self, market_price): return None
    @classmethod
    def from_leg(cls, underlying, exchange, expiry, strike, right, leg, **kw):
        from datetime import datetime as _dt
        exp = expiry if isinstance(expiry, date) else _dt.strptime(str(expiry), '%Y-%m-%d').date() if expiry else None
        iid = InstrumentId.option(exchange, underlying, exp, strike, right)
        return cls(iid, strike=strike, expiry=exp, right=right, leg=leg, **kw)


# ══════════════════════════════════════════════════════════════════════
# PHASE 3: DESIGN PRINCIPLES & FLOWS
# ══════════════════════════════════════════════════════════════════════

## 3.1 Core Design Principles

1. **Pure Domain Objects** — Instrument, Option, OptionChain own behavior directly. No aggregate roots wrapping value objects.

2. **Ports Not Adapters** — Domain depends on abstract DataProvider/ExecutionProvider. Concrete implementations live in providers/.

3. **Broker Is Infrastructure** — Gateway, auth, WebSocket, REST are internal. Never exposed to user layer.

4. **Indicators Outside Brokers** — RSI, MACD, VWAP are in plugins/indicators/. Domain loads them via facade.

5. **No Wrappers** — Every new class is written fresh. Old code is deleted, not adapted.

6. **Composition Over Inheritance** — Instrument contains Quote, Depth, Subscription. Not inherits.

7. **Single State Owner** — Instrument owns its state. Provider updates it. No global state.

8. **Thread Safety** — State mutations are atomic (replace entire state object under lock).

---

## 3.2 Object Flow Diagrams

### Flow 1: Instrument Creation

```
User Code                    Composition Root              Domain
─────────                    ─────────────────             ──────
                             
nifty = Index("NIFTY")  ──>  provider = DhanDataProvider(gateway)
                             set_default_provider(provider)
                             
                             Instrument(
                               InstrumentId.index("NSE", "NIFTY"),
                               data_provider=provider,
                             )
                             
                        <──  Instrument object created
```

### Flow 2: Quote Fetch

```
nifty.ltp                      
  │                             
  ├─> self._state.quote        (cached state)
  │   if None:                 
  │     ├─> provider.get_quote(instrument_id)
  │     │     │                
  │     │     ├─> gateway.quote(symbol, exchange)
  │     │     │     │          
  │     │     │     ├─> rate_limiter.acquire("quotes")
  │     │     │     ├─> circuit_breaker.check()
  │     │     │     ├─> dhanhq.ticker_data(...)
  │     │     │     └─> normalize response
  │     │     │                
  │     │     └─< QuoteSnapshot
  │     │                       
  │     └─> self._state = InstrumentState(quote=q)
  │                             
  └─< self._state.quote.ltp   (return value)
```

### Flow 3: Subscribe to Live Data

```
nifty.subscribe(callback)
  │
  ├─> self._provider.subscribe(instrument_id, wrapped_callback)
  │     │
  │     ├─> gateway.stream(symbol, exchange, callback)
  │     │     │
  │     │     ├─> websocket_manager.subscribe(instrument)
  │     │     │     │
  │     │     │     ├─> shared_websocket.send(subscribe_message)
  │     │     │     └─< SubscriptionHandle
  │     │     │
  │     │     └─< handle
  │     │
  │     └─< SubscriptionHandle
  │
  └─< handle

--- Later, on each tick ---

shared_websocket.on_message(data)
  │
  ├─> dispatch to per-instrument callbacks
  │     │
  │     ├─> wrapped_callback(instrument_id, QuoteSnapshot)
  │     │     │
  │     │     ├─> self._state = InstrumentState(quote=q, last_tick=q)
  │     │     ├─> for cb in self._callbacks["tick"]: cb(payload)
  │     │     └─> callback(instrument_id, payload)
  │     │
  │     └─> event_bus.publish("TICK", {...})
```

### Flow 4: Order Placement

```
nifty.buy(quantity=10, price=Decimal("2450"))
  │
  ├─> self._executor.place_order(OrderRequest(...))
  │     │
  │     ├─> gateway.place_order(request)
  │     │     │
  │     │     ├─> rate_limiter.acquire("orders")
  │     │     ├─> circuit_breaker.check()
  │     │     ├─> static_ip_check()
  │     │     ├─> dhanhq.place_order(...)
  │     │     └─< OrderResponse
  │     │
  │     └─< OrderResponse
  │
  └─< OrderResponse
```

### Flow 5: Option Chain

```
nifty.option_chain()
  │
  ├─> self._provider.get_option_chain(instrument_id)
  │     │
  │     ├─> gateway.option_chain("NIFTY", "NFO", expiry)
  │     │     │
  │     │     ├─> dhanhq.option_chain(...)
  │     │     └─< raw chain data
  │     │
  │     └─< OptionChain value object
  │
  └─> OptionChain(chain_vo, provider=self._provider)
        │
        ├─> chain.atm  (creates Option from leg)
        ├─> chain.calls  (creates Options from legs)
        └─> chain.puts   (creates Options from legs)
```

---

## 3.3 Internal Package Organization

```
src/domain/                          # PUBLIC: User-facing objects
├── instruments/
│   ├── instrument.py               # Instrument, Equity, Index, Future, Option
│   ├── instrument_id.py            # InstrumentId (identity)
│   └── subscription.py             # Subscription (live data)
├── options/
│   ├── option_chain.py             # OptionChain (rich queries)
│   └── greeks.py                   # Greeks (value object)
├── ports/
│   ├── data_provider.py            # DataProvider ABC (new)
│   ├── execution_provider.py       # ExecutionProvider ABC (new)
│   └── subscription_handle.py      # SubscriptionHandle ABC (new)
├── entities/                        # KEEP: Value objects
├── enums.py                         # KEEP
└── errors.py                        # KEEP

providers/                           # NEW: Broker adapter implementations
├── __init__.py
├── dhan/
│   ├── __init__.py
│   ├── data_provider.py            # DhanDataProvider (implements DataProvider)
│   ├── execution_provider.py       # DhanExecutionProvider (implements ExecutionProvider)
│   └── extension.py                # DhanExtension (broker-specific features)
├── upstox/
│   ├── __init__.py
│   ├── data_provider.py            # UpstoxDataProvider
│   ├── execution_provider.py       # UpstoxExecutionProvider
│   └── extension.py                # UpstoxExtension
├── csv/
│   └── data_provider.py            # CsvDataProvider (tests/notebooks)
├── replay/
│   └── data_provider.py            # ReplayDataProvider (backtest)
└── composite/
    └── data_provider.py            # CompositeDataProvider (fallback chain)

brokers/                             # INTERNAL: Gateway, auth, transport
├── dhan/
│   ├── gateway.py                  # DhanGateway (raw API wrapper)
│   ├── http_client.py              # HTTP client
│   ├── config.py                   # Configuration
│   ├── auth.py                     # Dhan-specific auth
│   └── resilience/                 # Rate limiting, circuit breaker
├── upstox/
│   ├── gateway.py                  # UpstoxGateway
│   ├── http_client.py
│   ├── config.py
│   ├── auth.py
│   └── resilience/
└── common/
    ├── auth/                       # AuthManager, TokenState, TokenStore
    ├── resilience/                 # RateLimiter, CircuitBreaker, Retry
    ├── factory.py                  # BrokerFactory
    └── bootstrap.py                # Bootstrap wiring

plugins/indicators/                  # OUTSIDE brokers: Analytics
├── rsi.py
├── macd.py
├── vwap.py
├── atr.py
└── supertrend.py

domain/indicators/                   # Facade that loads plugins
└── indicators.py
```

---

## 3.4 Broker Capability Extension Architecture

### How Extensions Work

1. Each broker defines an Extension class in `providers/{broker}/extension.py`
2. Extension declares capabilities (depth20, depth200, super_order, etc.)
3. Extension is registered at composition root
4. User accesses via `instrument.broker.depth20()`

### Extension Registration Flow

```
Composition Root:
  1. Create DhanGateway
  2. Create DhanDataProvider(gateway)
  3. Create DhanExtension(gateway)
  4. Register extension with provider
  5. Wire provider into domain

User Code:
  stock = Equity("RELIANCE")
  stock.broker.depth20()  # Calls DhanExtension.depth20()
```

### Extension Interface

```
Extension ABC:
  - name: str
  - capabilities: list[Capability]
  - supports(feature: str) -> bool

DhanExtension:
  - depth20(symbol, exchange) -> MarketDepth
  - depth200(symbol, exchange) -> MarketDepth
  - super_order(request) -> OrderResponse
  - forever_order(request) -> OrderResponse

UpstoxExtension:
  - depth30(symbol, exchange) -> MarketDepth
  - option_greeks_stream(callback) -> Subscription
  - full_market_quote(symbol, exchange) -> QuoteSnapshot
```

---

## 3.5 OptionChain Design

### Composition

```
OptionChain (value object)
  ├── underlying: str
  ├── exchange: str
  ├── expiry: str
  ├── spot: Decimal
  └── strikes: list[OptionStrike]
      ├── strike: Decimal
      ├── call: OptionLeg (ltp, iv, oi, greeks)
      └── put: OptionLeg (ltp, iv, oi, greeks)

OptionChain (rich wrapper — domain object)
  ├── _chain: OptionChainVO (value object)
  ├── _provider: DataProvider
  └── _options: dict[tuple, Option] (cached)
      ├── calls -> list[Option]
      ├── puts -> list[Option]
      └── atm -> Option
```

### Query Methods

```
chain.atm          -> Option (ATM call)
chain.calls        -> list[Option] (all calls)
chain.puts         -> list[Option] (all puts)
chain.expiries     -> tuple[str]
chain.itm()        -> list[Option]
chain.otm()        -> list[Option]
chain.pcr()        -> Decimal
chain.max_pain()   -> Decimal
chain.iv_surface() -> DataFrame
chain.greeks()     -> DataFrame
chain.subscribe()  -> Subscription
chain.refresh()    -> OptionChain
```

---

## 3.6 Historical and Live Data Lifecycle

### Historical Data Lifecycle

```
1. User calls instrument.history(timeframe="5m", days=20)
2. Instrument calls provider.get_history(instrument_id, ...)
3. Provider calls gateway.history(symbol, exchange, ...)
4. Gateway calls dhanhq API
5. Response normalized to DataFrame
6. DataFrame wrapped in HistoricalSeries(instrument)
7. HistoricalSeries returned to user

HistoricalSeries methods:
  - cached() -> DataFrame (from cache)
  - download() -> DataFrame (force fetch)
  - refresh() -> DataFrame (update cache)
  - resample(timeframe) -> HistoricalSeries
  - indicators(*names) -> DataFrame
```

### Live Data Lifecycle

```
1. User calls instrument.subscribe(callback)
2. Instrument creates Subscription object
3. Instrument calls provider.subscribe(instrument_id, wrapped_callback)
4. Provider calls gateway.stream(symbol, exchange, callback)
5. Gateway subscribes to WebSocket
6. WebSocket manager shares connection across instruments
7. On each tick: wrapped_callback updates Instrument state
8. User callback invoked with payload
9. Domain events published (TICK, DEPTH_UPDATED)

Subscription methods:
  - is_active -> bool
  - tick_count -> int
  - depth_count -> int
  - on_tick(callback) -> None
  - on_depth(callback) -> None
  - unsubscribe() -> None
```

---

## 3.7 Subscription Architecture

### Shared WebSocket Management

```
WebSocketManager (internal)
  ├── connections: dict[str, WebSocket] (per exchange)
  ├── subscriptions: dict[InstrumentId, list[Callback]]
  └── methods:
      - subscribe(instrument_id, callback) -> SubscriptionHandle
      - unsubscribe(handle) -> None
      - reconnect(exchange) -> None

Flow:
  1. First subscription to NSE creates WebSocket connection
  2. Subsequent NSE subscriptions reuse same connection
  3. Messages dispatched to per-instrument callbacks
  4. On disconnect: automatic reconnect, resume subscriptions
```

### Subscription States

```
IDLE -> SUBSCRIBING -> SUBSCRIBED -> UNSUBSCRIBING -> UNSUBSCRIBED
         |                                      ^
         └-> ERROR ----------------------------┘
```

---

## 3.8 Design Pattern Justification

| Pattern | Where | Why |
|---------|-------|-----|
| Strategy | DataProvider, ExecutionProvider | Swap implementations without modifying domain |
| Adapter | DhanDataProvider wraps DhanGateway | Normalize broker API into common interface |
| Factory | BrokerFactory, InstrumentFactory | Create objects without exposing construction |
| Observer | Subscription callbacks, EventBus | Decouple live data from consumers |
| State | Subscription lifecycle | Explicit transitions (SUBSCRIBING->SUBSCRIBED) |
| Facade | Instrument hides provider complexity | Simple API over complex internals |
| Flyweight | InstrumentId (frozen, shared) | Immutable identity, hashable |
| Composite | CompositeDataProvider | Fallback chain of providers |
| Decorator | CacheDataProvider wraps real provider | Add caching without modifying core |
| Proxy | Lazy instrument loading | Deferred provider resolution |

---

# ══════════════════════════════════════════════════════════════════════
# PHASE 4: TDD IMPLEMENTATION PLAN
# ══════════════════════════════════════════════════════════════════════

## 4.1 Test Pyramid

```
                    ┌─────────────────┐
                    │   E2E Tests     │  5%  (live broker, real API)
                    │  (contract)     │
                    ├─────────────────┤
                    │ Integration     │ 15%  (provider + mock gateway)
                    │ Tests           │
                    ├─────────────────┤
                    │ Unit Tests      │ 80%  (pure domain, no I/O)
                    │ (domain)        │
                    └─────────────────┘
```

### Unit Tests (80%)

- Instrument creation and identity
- Instrument state updates
- Option chain queries (atm, calls, puts, pcr, max_pain)
- Greeks computation
- Order request construction
- Subscription lifecycle
- HistoricalSeries methods
- Serialization

### Integration Tests (15%)

- Provider + mock gateway (quote fetch, history fetch)
- Provider + mock WebSocket (subscribe, tick dispatch)
- Option chain construction from mock data
- Order placement through provider
- Composite provider fallback

### E2E Tests (5%)

- Live Dhan connection (requires credentials)
- Live Upstox connection (requires credentials)
- Real order placement (paper mode)
- Real WebSocket subscription

---

## 4.2 TDD Workflow Per Phase

### Phase 1: Ports (TDD)

```
RED:   Write test for DataProvider interface
       assert DataProvider is abstract
       assert get_quote is abstract method
       
GREEN: Create DataProvider ABC with abstract methods
       
REFACTOR: Extract SubscriptionHandle ABC
```

### Phase 2: Instrument (TDD)

```
RED:   Write test: Equity("RELIANCE").symbol == "RELIANCE"
       Write test: Equity("RELIANCE").exchange == "NSE"
       Write test: Equity("RELIANCE").ltp is None (no provider)
       
GREEN: Create Instrument, Equity, Index classes with identity
       
RED:   Write test: Equity("RELIANCE", provider=mock).ltp == Decimal("2450")
       Write test: Equity("RELIANCE", provider=mock).refresh() updates state
       
GREEN: Implement refresh(), history(), depth() delegating to provider
       
RED:   Write test: Equity("RELIANCE").buy(10, price=2450) calls executor
       Write test: Equity("RELIANCE").sell(10) calls executor with SELL
       
GREEN: Implement buy(), sell(), market(), limit(), stop_loss()
       
RED:   Write test: subscribe() updates state and invokes callback
       Write test: on_tick() registers callback
       
GREEN: Implement subscribe(), unsubscribe(), on_tick(), on_quote()
```

### Phase 3: OptionChain (TDD)

```
RED:   Write test: chain.atm returns Option with correct strike
       Write test: chain.calls returns list of Options
       Write test: chain.pcr() computes put/call OI ratio
       Write test: chain.max_pain() computes correct strike
       
GREEN: Implement OptionChain with all query methods
```

### Phase 4: Providers (TDD)

```
RED:   Write test: DhanDataProvider.get_quote() calls gateway
       Write test: DhanDataProvider.subscribe() returns SubscriptionHandle
       Write test: DhanExecutionProvider.place_order() calls gateway
       
GREEN: Implement DhanDataProvider, DhanExecutionProvider
       
RED:   Write test: CompositeDataProvider falls back to second provider
       Write test: CsvDataProvider reads from CSV file
       
GREEN: Implement CompositeDataProvider, CsvDataProvider
```

### Phase 5: Extensions (TDD)

```
RED:   Write test: DhanExtension.depth20() calls gateway
       Write test: DhanExtension.supports("depth20") returns True
       Write test: DhanExtension.supports("depth300") returns False
       
GREEN: Implement DhanExtension, UpstoxExtension
```

---

## 4.3 Test File Organization

```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_instrument.py
│   │   ├── test_equity.py
│   │   ├── test_index.py
│   │   ├── test_future.py
│   │   ├── test_option.py
│   │   ├── test_option_chain.py
│   │   ├── test_greeks.py
│   │   ├── test_subscription.py
│   │   └── test_instrument_id.py
│   ├── ports/
│   │   ├── test_data_provider.py
│   │   └── test_execution_provider.py
│   └── indicators/
│       └── test_rsi.py
├── integration/
│   ├── providers/
│   │   ├── test_dhan_data_provider.py
│   │   ├── test_dhan_execution_provider.py
│   │   ├── test_composite_provider.py
│   │   └── test_csv_provider.py
│   ├── domain/
│   │   ├── test_instrument_with_provider.py
│   │   ├── test_option_chain_with_provider.py
│   │   └── test_subscription_with_provider.py
│   └── extensions/
│       ├── test_dhan_extension.py
│       └── test_upstox_extension.py
└── contract/
    ├── test_dhan_live.py
    ├── test_upstox_live.py
    └── test_broker_contract.py
```

---

## 4.4 Adoption Plan (Step by Step)

### Step 1: Create New Ports (Day 1)

- Create `src/domain/ports/data_provider.py` (new ABC)
- Create `src/domain/ports/execution_provider.py` (new ABC)
- Create `src/domain/ports/subscription_handle.py` (new ABC)
- Write unit tests for interface contracts
- Do NOT touch existing code yet

### Step 2: Create New Instrument (Day 2-3)

- Create `src/domain/instruments/instrument.py` (new, replacing old)
- Implement Instrument, Equity, Index, Future, Option
- Write unit tests for identity, state, behaviors
- Write unit tests for orders (mock executor)
- Do NOT touch existing code yet

### Step 3: Create New OptionChain (Day 3-4)

- Create `src/domain/options/option_chain.py` (new, replacing old)
- Implement OptionChain with all query methods
- Write unit tests for atm, calls, puts, pcr, max_pain
- Do NOT touch existing code yet

### Step 4: Create Providers (Day 5-7)

- Create `providers/dhan/data_provider.py`
- Create `providers/dhan/execution_provider.py`
- Create `providers/upstox/data_provider.py`
- Create `providers/upstox/execution_provider.py`
- Write integration tests with mock gateways

### Step 5: Create Extensions (Day 8)

- Create `providers/dhan/extension.py`
- Create `providers/upstox/extension.py`
- Write unit tests for capability checks

### Step 6: Create Composition Root (Day 9)

- Create `brokers/common/factory.py` (new)
- Create `brokers/common/bootstrap.py` (new)
- Wire everything together
- Write integration tests

### Step 7: Migrate Tests (Day 10)

- Migrate existing tests to use new objects
- Delete old test fixtures
- Ensure all tests pass

### Step 8: Delete Old Code (Day 11)

- Delete old instrument.py, subscription.py, option_chain.py
- Delete old adapters (brokers/dhan/adapter.py, etc.)
- Delete old factory, bootstrap, infrastructure
- Update imports across codebase
- Run full test suite

### Step 9: Update CLI/API (Day 12)

- Update CLI commands to use new Instrument API
- Update REST endpoints to use new objects
- Write integration tests

### Step 10: Documentation (Day 13)

- Write API reference for new objects
- Write migration guide
- Write examples

---

## 4.5 Success Criteria

- [ ] `Equity("RELIANCE").ltp` works
- [ ] `Index("NIFTY").subscribe(callback)` works
- [ ] `nifty.option_chain().atm.greeks.delta` works
- [ ] `nifty.buy(quantity=10, price=2450)` works
- [ ] `stock.broker.depth20()` works for Dhan
- [ ] All existing tests pass
- [ ] No imports from brokers.* in domain/
- [ ] No adapters wrapping old code
- [ ] Test pyramid: 80% unit, 15% integration, 5% E2E