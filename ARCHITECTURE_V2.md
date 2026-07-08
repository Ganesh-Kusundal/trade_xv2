# TradeXV2 — Architecture V2: Instrument-Centric Design

> **Status:** Design Proposal  
> **Date:** July 2026  
> **Supersedes:** ARCHITECTURE.md (V1)  
> **Scope:** Application, Domain, Analytics layers. Broker SDK changes excluded.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Critique](#2-current-architecture-critique)
3. [Design Principles](#3-design-principles)
4. [Core Concept: Instrument as Aggregate Root](#4-core-concept-instrument-as-aggregate-root)
5. [Domain Model](#5-domain-model)
6. [Provider Framework](#6-provider-framework)
7. [Extension System](#7-extension-system)
8. [Package Structure](#8-package-structure)
9. [Public API Design](#9-public-api-design)
10. [Internal Architecture](#10-internal-architecture)
11. [Event Flow Redesign](#11-event-flow-redesign)
12. [Testing Architecture](#12-testing-architecture)
13. [Migration Plan](#13-migration-plan)
14. [Decision Log](#14-decision-log)

---

## 1. Executive Summary

### The Problem

TradeXV2 has a strong layered architecture, but the **domain model is anemic**. The current `Instrument` is a frozen dataclass with 12 fields and zero behavior. Market data, analytics, and execution are accessed through scattered protocols and service objects rather than through rich domain objects. This creates several problems:

- **No central abstraction:** Consumers must know which service to call for each operation (MarketDataProvider for quotes, BrokerGateway for orders, Analytics for signals). There is no single entry point.
- **Broker-specific leakage:** The `Capability` enum in `domain/capabilities.py` lists 40+ broker-specific features. Domain code shouldn't know about broker internals.
- **Provider confusion:** There are three overlapping provider concepts: `MarketDataPort` (domain), `MarketDataProvider` (analytics), and `BrokerGateway` (brokers). They serve similar purposes with different interfaces.
- **No capability discovery:** The feature matrix is hardcoded. New brokers require manual updates across multiple files.
- **Analytics is disconnected:** The `Analytics` facade owns lazy engine instances but has no awareness of instruments — it operates on raw DataFrames and dicts.

### The Solution

Make **Instrument the Aggregate Root** that the entire system revolves around. Instrument owns identity and state, delegates behavior to injected Providers, and exposes capabilities through a clean Extension system. This is **not** about making Instrument a God Object — it's about making Instrument the **entry point** while keeping actual logic in focused, testable services.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Aggregate Root | `InstrumentAggregate` | Central abstraction, every module works with it |
| Data access | Provider Registry | Same instrument, multiple data sources |
| Broker capabilities | Extension Registry | Runtime discovery, no hardcoded feature matrix |
| Domain services | Dedicated layer | Separate orchestration from entity state |
| Analytics integration | Instrument-aware engines | Engines accept Instrument, not raw DataFrames |

---

## 2. Current Architecture Critique

### 2.1 Strengths (Keep These)

| Component | Why It's Good |
|-----------|---------------|
| **Layered architecture** | Clear dependency direction, import-linter enforced |
| **Event bus** | Thread-safe, typed events, dead-letter queue, correlation IDs |
| **OMS pipeline** | Idempotent placement, risk gates, state validation, audit logging |
| **Protocol-based ports** | Structural typing via `@runtime_checkable Protocol` |
| **InstrumentId** | Canonical identity format, parse/serialize, exchange-normalized |
| **LifecycleManager** | Deterministic startup/shutdown for all background services |
| **Resilience patterns** | Circuit breaker, rate limiter, retry with exponential backoff |

### 2.2 Weaknesses (Fix These)

| Weakness | Current State | Impact |
|----------|---------------|--------|
| **Anemic Instrument** | 12-field frozen dataclass, no methods | Every consumer must extract fields and operate on them externally |
| **Triple provider pattern** | `MarketDataPort` + `MarketDataProvider` + `BrokerGateway` | Confusing which interface to use; adapter boilerplate everywhere |
| **Hardcoded capabilities** | `Capability` enum with 40+ values | Adding a broker feature requires editing domain code |
| **Scattered state** | Quote lives in gateway, History lives in datalake, Depth lives in websocket adapter | No single place to get "the current state of this instrument" |
| **Analytics disconnected** | `Analytics` facade wraps engines that accept DataFrames | No instrument-awareness; must manually fetch data, then pass to engine |
| **No extension model** | Broker-specific features (depth200, forever orders) require `if broker == dhan` checks | Violates Open/Closed Principle |
| **Mixed responsibility** | `OptionChain` has `from_dict()` parsing logic inside the entity | Parsing belongs in adapters, not domain entities |

### 2.3 Architectural Debt

```
Current import direction (correct):
  domain ← application ← cli
  domain ← infrastructure ← brokers

Current provider confusion:
  MarketDataPort (domain/ports/)      → history, option_chain, future_chain, ltp
  MarketDataProvider (analytics/core/) → history, option_chain, future_chain, ltp
  BrokerGateway (brokers/common/)      → ltp, quote, history, depth, option_chain, place_order

Three interfaces, nearly identical methods, different return types.
```

---

## 3. Design Principles

These principles guide every decision in Architecture V2:

### P1: Instrument is the Entry Point
Every module should be able to work with `Instrument` objects. If a consumer needs market data, it asks the instrument. If it needs to place an order, it asks the instrument. The instrument delegates to the appropriate provider.

### P2: Composition Over Inheritance
Instrument does NOT inherit from MarketDataProvider or ExecutionProvider. It **has** providers injected via constructor. This keeps Instrument thin and testable.

### P3: Providers Replace Direct Broker References
No domain or application code should reference `DhanGateway`, `UpstoxGateway`, or any broker-specific type. All access goes through `DataProvider` or `ExecutionProvider` protocols.

### P4: Extensions for Broker-Specific Features
Broker-specific capabilities (depth200, forever orders, super orders) are modeled as `Extension` objects registered at startup. Domain code queries extensions by name, never by broker type.

### P5: Immutable Where Appropriate
Value objects (`InstrumentState`, `Quote`, `Money`) are frozen. Aggregate state (`InstrumentAggregate`) uses internal mutability with thread-safe accessors.

### P6: Event-Driven Communication
Cross-cutting concerns (logging, metrics, audit) subscribe to domain events. Instrument state changes publish events. No direct method calls for cross-module communication.

---

## 4. Core Concept: Instrument as Aggregate Root

### 4.1 Why Instrument?

The pasted text proposes Instrument as the central abstraction. This is correct for a trading system because:

1. **Every operation involves an instrument.** You fetch data for an instrument, place orders for an instrument, analyze an instrument, hold positions in instruments.
2. **Instruments have unique identity.** The `InstrumentId` (exchange:underlying:expiry:strike:right) is already the canonical identifier.
3. **Instruments have lifecycle.** An instrument goes through states: discovered → subscribed → quoted → traded → archived.
4. **Instruments compose naturally.** An OptionChain contains Instruments. A Position references an Instrument. An Order targets an Instrument.

### 4.2 What Instrument Is NOT

Instrument is **not** a God Object. It does NOT:
- Own market data storage (providers do)
- Execute trades (execution providers do)
- Compute analytics (analytics engines do)
- Store order history (order repository does)

Instrument IS:
- The **identity** that everything references
- The **state holder** for current quote, depth, subscription
- The **delegation point** that routes requests to the right provider
- The **capability query point** that exposes what this instrument can do

### 4.3 Aggregate Boundary

```
┌──────────────────────────────────────────────────────────────┐
│                    InstrumentAggregate                        │
│                    (Aggregate Root)                           │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Identity (Value Object)                             │    │
│  │  • InstrumentId                                      │    │
│  │  • InstrumentType (Equity, Future, Option, ...)      │    │
│  │  • Exchange                                          │    │
│  │  • Metadata (lot_size, tick_size, name)              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  State (Value Object — immutable snapshots)          │    │
│  │  • InstrumentState                                    │    │
│  │    - quote: QuoteSnapshot | None                     │    │
│  │    - depth: MarketDepth | None                       │    │
│  │    - subscription: SubscriptionState                 │    │
│  │    - last_update: datetime | None                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Providers (Injected — not owned)                    │    │
│  │  • data_provider: DataProvider                       │    │
│  │  • execution_provider: ExecutionProvider | None      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Extensions (Composed — not inherited)               │    │
│  │  • _extensions: list[Extension]                      │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘

References (by identity only, NOT by object reference):
  ├── Order.instrument_id → InstrumentId
  ├── Position.instrument_id → InstrumentId
  ├── Holding.instrument_id → InstrumentId
  ├── Trade.instrument_id → InstrumentId
  └── OptionChain.underlying → str (symbol)
```

### 4.4 Consistency Rules

Within the InstrumentAggregate boundary:
- State transitions are atomic (thread-safe via internal lock)
- Quote updates replace the entire QuoteSnapshot (never partial)
- Subscription state changes publish SUBSCRIPTION_CHANGED events
- Extension queries are read-only (no mutation)

---

## 5. Domain Model

### 5.1 Aggregate Roots

There are exactly **5 Aggregate Roots** in the system:

| Aggregate | Identity | State | Owns |
|-----------|----------|-------|------|
| **InstrumentAggregate** | `InstrumentId` | `InstrumentState` | Identity, state, providers (ref), extensions (ref) |
| **AccountAggregate** | `account_id: str` | `AccountState` | Balance, fund limits, positions (by ref) |
| **OrderAggregate** | `order_id: str` | `OrderState` | Order lifecycle, trades (by composition) |
| **PositionAggregate** | `(account_id, instrument_id)` | `PositionState` | Quantity, avg price, realized PnL |
| **OptionChainAggregate** | `(underlying, expiry)` | `OptionChainState` | Strikes, Greeks, ATM/ITM/OTM queries |

### 5.2 Value Objects

```python
# ── Identity Value Objects ──────────────────────────────────────────

@dataclass(frozen=True, order=True)
class InstrumentId:
    """Canonical instrument identity. ALREADY EXISTS — keep as-is."""
    exchange: str
    underlying: str
    expiry: date | None = None
    strike: Decimal | None = None
    right: str | None = None

# ── Market Data Value Objects ───────────────────────────────────────

@dataclass(frozen=True)
class QuoteSnapshot:
    """Point-in-time quote with provenance. ALREADY EXISTS — keep as-is."""
    instrument: InstrumentRef
    ltp: Decimal
    event_time: datetime
    provenance: DataProvenance
    # ... other fields

@dataclass(frozen=True)
class InstrumentState:
    """Current state of an instrument — immutable snapshot.
    
    NEW — replaces scattered state across gateway/websocket/cache.
    Thread-safety: the Aggregate replaces the entire state atomically.
    """
    quote: QuoteSnapshot | None = None
    depth: MarketDepth | None = None
    subscription: SubscriptionState = SubscriptionState.UNSUBSCRIBED
    last_update: datetime | None = None
    error: str | None = None

@dataclass(frozen=True)
class SubscriptionState:
    """Subscription lifecycle — Value Object."""
    status: str = "UNSUBSCRIBED"  # UNSUBSCRIBED, SUBSCRIBING, SUBSCRIBED, ERROR
    symbol: str = ""
    exchange: str = ""
    started_at: datetime | None = None
    error: str | None = None

# ── Financial Value Objects ─────────────────────────────────────────

@dataclass(frozen=True)
class Money:
    """Monetary amount with currency — NEW."""
    amount: Decimal
    currency: str = "INR"

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(amount=self.amount + other.amount, currency=self.currency)

@dataclass(frozen=True)
class TickSize:
    """Price tick size awareness — NEW."""
    value: Decimal = Decimal("0.05")

    def round_price(self, price: Decimal) -> Decimal:
        """Round price to nearest tick."""
        return (price / self.value).quantize(Decimal("1")) * self.value

# ── Capability Value Objects ────────────────────────────────────────

@dataclass(frozen=True)
class Capability:
    """What an instrument/provider can do — NEW.
    
    Replaces the hardcoded Capability enum with runtime-discoverable
    capabilities.
    """
    name: str
    supported: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Extension:
    """Broker-specific capability — NEW.
    
    Extensions are registered at startup and queried by name.
    No `if broker == dhan` logic anywhere.
    """
    name: str           # e.g., "depth200", "forever_orders"
    broker: str         # e.g., "dhan", "upstox"
    version: str = "1.0"
    capabilities: tuple[Capability, ...] = ()
```

### 5.3 Entities (Non-Aggregate)

These entities live **inside** an Aggregate boundary:

| Entity | Inside Aggregate | Identity |
|--------|-----------------|----------|
| `Trade` | OrderAggregate | trade_id |
| `DepthLevel` | InstrumentAggregate (inside MarketDepth) | price level |
| `OptionStrike` | OptionChainAggregate | strike price |
| `OptionLeg` | OptionChainAggregate (inside OptionStrike) | CE/PE |
| `Holding` | AccountAggregate | instrument_id |

### 5.4 Relationships

```
InstrumentAggregate ──(1:N)──→ OrderAggregate
    │                              │
    │ instrument_id                │ instrument_id
    │                              │
    └──(1:N)──→ PositionAggregate ←┘
    │
    └──(1:N)──→ OptionChainAggregate
                    │
                    └──(1:N)──→ OptionStrike
                                    │
                                    └──(1:2)──→ OptionLeg (call, put)

AccountAggregate ──(1:N)──→ PositionAggregate
AccountAggregate ──(1:N)──→ Holding
```

### 5.5 Entity Lifecycle

```
InstrumentAggregate:
  DISCOVERED → SUBSCRIBING → SUBSCRIBED → ACTIVE → STALE → ARCHIVED
      │              │            │          │        │
      │              │            │          │        └─ No updates for TTL
      │              │            │          └─ Processing trades
      │              │            └─ Receiving live ticks
      │              └─ WebSocket connecting
      └─ Added to universe

OrderAggregate:
  CREATED → RISK_CHECK → SUBMITTED → OPEN → PARTIAL → FILLED
                                          → CANCELLED
                                          → REJECTED
                                          → EXPIRED

PositionAggregate:
  OPEN → INCREASING → DECREASING → CLOSED
```

---

## 6. Provider Framework

### 6.1 Provider Hierarchy

The pasted text proposes replacing Broker with Provider as the central abstraction. We adopt a **lighter version**: Provider becomes the data/execution layer, but Instrument remains the user-facing entry point.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Provider Hierarchy                                 │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    ProviderRegistry                          │    │
│  │  • data_providers: dict[str, DataProvider]                  │    │
│  │  • execution_providers: dict[str, ExecutionProvider]        │    │
│  │  • default_provider: str                                    │    │
│  │                                                              │    │
│  │  Methods:                                                    │    │
│  │  • register(name, provider)                                 │    │
│  │  • get_data_provider(name | None) → DataProvider            │    │
│  │  • get_execution_provider(name | None) → ExecutionProvider  │    │
│  └──────────────┬──────────────────────────────────────────────┘    │
│                  │                                                    │
│       ┌──────────┴──────────┐                                        │
│       ▼                     ▼                                        │
│  ┌──────────┐         ┌──────────────┐                              │
│  │  Data    │         │  Execution   │                              │
│  │ Provider │         │  Provider    │                              │
│  │ Protocol │         │  Protocol    │                              │
│  └────┬─────┘         └──────┬───────┘                              │
│       │                      │                                       │
│  ┌────┴─────────────────────┐│                                       │
│  │ Implementations:         ││                                       │
│  │ • BrokerDataProvider     ││                                       │
│  │ • CsvDataProvider        ││                                       │
│  │ • ReplayDataProvider     ││                                       │
│  │ • CacheDataProvider      ││                                       │
│  │ • CompositeDataProvider  ││                                       │
│  │ • DataFrameDataProvider  ││                                       │
│  └──────────────────────────┘│                                       │
│                               │                                       │
│  ┌───────────────────────────┘                                       │
│  │ Implementations:                                                  │
│  │ • BrokerExecutionProvider                                         │
│  │ • PaperExecutionProvider                                          │
│  │ • SimulatedExecutionProvider                                      │
│  └───────────────────────────────────────────────────────────────────┘
```

### 6.2 Provider Protocols

```python
# ── domain/providers/protocols.py ──────────────────────────────────

class DataProvider(Protocol):
    """Central data access protocol.
    
    Replaces MarketDataPort, MarketDataProvider, and parts of BrokerGateway
    with a single, unified interface.
    """
    
    @property
    def name(self) -> str:
        """Provider name for logging and registry lookup."""
        ...
    
    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        """Get latest quote for an instrument."""
        ...
    
    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Get historical OHLCV bars."""
        ...
    
    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        """Get market depth (order book)."""
        ...
    
    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        """Get option chain for an underlying."""
        ...
    
    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        """Get futures chain for an underlying."""
        ...
    
    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, QuoteSnapshot], None],
        *,
        depth: bool = False,
    ) -> Subscription:
        """Subscribe to live market data."""
        ...
    
    def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe from live market data."""
        ...


class ExecutionProvider(Protocol):
    """Central execution access protocol.
    
    Replaces scattered order placement across broker gateways.
    """
    
    @property
    def name(self) -> str: ...
    
    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order."""
        ...
    
    def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order."""
        ...
    
    def modify_order(self, request: ModifyOrderRequest) -> OrderResult:
        """Modify an order."""
        ...
    
    def get_order_book(self) -> list[Order]:
        """Get all orders."""
        ...
    
    def get_positions(self) -> list[Position]:
        """Get current positions."""
        ...
    
    def get_holdings(self) -> list[Holding]:
        """Get current holdings."""
        ...
    
    def get_funds(self) -> FundLimits:
        """Get fund limits."""
        ...
```

### 6.3 Provider Registry

```python
# ── domain/providers/registry.py ───────────────────────────────────

class ProviderRegistry:
    """Central registry for all data and execution providers.
    
    This is the KEY architectural component. The registry is created
    at composition root and injected into all aggregates and services.
    
    Thread-safety: Registration is expected during startup (single-threaded).
    Lookup is lock-free (dict read).
    """
    
    def __init__(self) -> None:
        self._data_providers: dict[str, DataProvider] = {}
        self._execution_providers: dict[str, ExecutionProvider] = {}
        self._default_data: str = ""
        self._default_execution: str = ""
    
    def register_data_provider(self, name: str, provider: DataProvider) -> None:
        """Register a data provider. Call during startup."""
        self._data_providers[name] = provider
        if not self._default_data:
            self._default_data = name
    
    def register_execution_provider(self, name: str, provider: ExecutionProvider) -> None:
        """Register an execution provider. Call during startup."""
        self._execution_providers[name] = provider
        if not self._default_execution:
            self._default_execution = name
    
    def get_data_provider(self, name: str | None = None) -> DataProvider:
        """Get a data provider by name, or the default."""
        key = name or self._default_data
        if key not in self._data_providers:
            available = list(self._data_providers.keys())
            raise KeyError(f"Data provider '{key}' not registered. Available: {available}")
        return self._data_providers[key]
    
    def get_execution_provider(self, name: str | None = None) -> ExecutionProvider:
        """Get an execution provider by name, or the default."""
        key = name or self._default_execution
        if key not in self._execution_providers:
            available = list(self._execution_providers.keys())
            raise KeyError(
                f"Execution provider '{key}' not registered. Available: {available}"
            )
        return self._execution_providers[key]
    
    def list_data_providers(self) -> list[str]:
        """List all registered data provider names."""
        return list(self._data_providers.keys())
    
    def list_execution_providers(self) -> list[str]:
        """List all registered execution provider names."""
        return list(self._execution_providers.keys())
```

### 6.4 Provider Implementations

```python
# ── infrastructure/providers/broker/broker_data_provider.py ────────

class BrokerDataProvider:
    """Data provider backed by a live broker connection.
    
    Wraps the existing BrokerGateway (DhanGateway, UpstoxGateway)
    behind the DataProvider protocol.
    """
    
    def __init__(self, gateway: MarketDataGateway, name: str = "broker") -> None:
        self._gateway = gateway
        self._name = name
    
    @property
    def name(self) -> str:
        return self._name
    
    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        return self._gateway.quote(str(instrument_id))
    
    def get_history(self, instrument_id: InstrumentId, **kwargs) -> pd.DataFrame:
        return self._gateway.history(str(instrument_id), **kwargs)
    
    # ... etc


# ── infrastructure/providers/csv/csv_data_provider.py ──────────────

class CsvDataProvider:
    """Data provider backed by CSV files."""
    
    def __init__(self, path: str | Path, name: str = "csv") -> None:
        self._path = Path(path)
        self._name = name
        self._cache: dict[str, pd.DataFrame] = {}
    
    # ... implementation


# ── infrastructure/providers/composite/composite_provider.py ───────

class CompositeDataProvider:
    """Data provider that delegates to multiple providers with fallback.
    
    Example: Try broker first, fall back to CSV, then cache.
    """
    
    def __init__(self, providers: list[DataProvider]) -> None:
        self._providers = providers
    
    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        for provider in self._providers:
            try:
                result = provider.get_quote(instrument_id)
                if result is not None:
                    return result
            except Exception:
                continue
        return None
```

---

## 7. Extension System

### 7.1 Extension Framework

The pasted text proposes extensions as optional broker-specific capabilities. We implement this as a registry pattern:

```python
# ── domain/extensions/base.py ──────────────────────────────────────

class Extension(ABC):
    """Base class for broker-specific extensions.
    
    Extensions are registered at startup and discovered at runtime.
    Domain code never references broker-specific types.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Extension name (e.g., 'depth200', 'forever_orders')."""
        ...
    
    @property
    @abstractmethod
    def broker(self) -> str:
        """Broker this extension belongs to (e.g., 'dhan')."""
        ...
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Extension version for compatibility."""
        ...
    
    @abstractmethod
    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        """Check if this extension is available for a given instrument."""
        ...


# ── domain/extensions/registry.py ──────────────────────────────────

class ExtensionRegistry:
    """Registry for all broker-specific extensions.
    
    Extensions are registered during startup. Domain and application
    code queries the registry to discover capabilities.
    """
    
    def __init__(self) -> None:
        self._extensions: dict[str, Extension] = {}
    
    def register(self, extension: Extension) -> None:
        """Register an extension. Call during startup."""
        self._extensions[extension.name] = extension
    
    def get(self, name: str) -> Extension | None:
        """Get an extension by name."""
        return self._extensions.get(name)
    
    def has(self, name: str) -> bool:
        """Check if an extension is registered."""
        return name in self._extensions
    
    def available_for(self, instrument_id: InstrumentId) -> list[Extension]:
        """Get all extensions available for a given instrument."""
        return [
            ext for ext in self._extensions.values()
            if ext.is_available_for(instrument_id)
        ]
    
    def capabilities_for(self, instrument_id: InstrumentId) -> list[Capability]:
        """Get all capabilities available for a given instrument."""
        caps = []
        for ext in self.available_for(instrument_id):
            caps.extend(ext.capabilities)
        return caps
```

### 7.2 Concrete Extensions

```python
# ── infrastructure/extensions/dhan/depth200.py ─────────────────────

class Depth200Extension(Extension):
    """200-level market depth — Dhan-specific."""
    
    name = "depth200"
    broker = "dhan"
    version = "1.0"
    capabilities = (Capability(name="depth_200", supported=True),)
    
    def __init__(self, client: DhanHttpClient) -> None:
        self._client = client
    
    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return instrument_id.exchange in ("NSE", "NFO")
    
    async def get_depth_200(self, instrument_id: InstrumentId) -> MarketDepth:
        """Get 200-level depth."""
        ...


# ── infrastructure/extensions/dhan/forever_orders.py ───────────────

class ForeverOrderExtension(Extension):
    """GTT/Forever orders — Dhan-specific."""
    
    name = "forever_orders"
    broker = "dhan"
    version = "1.0"
    capabilities = (
        Capability(name="gtt_order", supported=True),
        Capability(name="oco_order", supported=True),
    )
    
    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return True  # Available for all Dhan instruments
    
    def place_forever_order(self, request: ForeverOrderRequest) -> str:
        ...


# ── infrastructure/extensions/upstox/advanced_quotes.py ────────────

class AdvancedQuotesExtension(Extension):
    """Advanced quotes with Greeks — Upstox-specific."""
    
    name = "advanced_quotes"
    broker = "upstox"
    version = "1.0"
    capabilities = (
        Capability(name="option_greeks", supported=True),
        Capability(name="depth_30", supported=True),
    )
    
    def is_available_for(self, instrument_id: InstrumentId) -> bool:
        return instrument_id.exchange in ("NSE", "NFO")
```

### 7.3 Extension Usage

```python
# Domain code — no broker imports
instrument = registry.get_instrument(InstrumentId.equity("NSE", "RELIANCE"))

# Query extensions by name
if extension_registry.has("depth200"):
    depth200_ext = extension_registry.get("depth200")
    if depth200_ext.is_available_for(instrument.id):
        deep_depth = await depth200_ext.get_depth_200(instrument.id)

# Or query all capabilities for an instrument
caps = extension_registry.capabilities_for(instrument.id)
for cap in caps:
    print(f"  {cap.name}: {cap.supported}")
```

---

## 8. Package Structure

### 8.1 New Package Layout

```
tradexv2/
│
├── domain/                          # ZERO external dependencies
│   ├── __init__.py                  # Re-exports all domain types
│   │
│   ├── aggregates/                  # NEW — Aggregate Roots
│   │   ├── __init__.py
│   │   ├── instrument.py           # InstrumentAggregate
│   │   ├── account.py              # AccountAggregate
│   │   ├── order.py                # OrderAggregate
│   │   ├── position.py             # PositionAggregate
│   │   └── option_chain.py         # OptionChainAggregate
│   │
│   ├── value_objects/               # NEW — All Value Objects
│   │   ├── __init__.py
│   │   ├── identity.py             # InstrumentId (moved from instrument_id.py)
│   │   ├── market.py               # QuoteSnapshot, MarketDepth, DepthLevel
│   │   ├── money.py                # Money, TickSize
│   │   ├── time_vo.py              # Timestamp, TimeRange
│   │   ├── state.py                # InstrumentState, SubscriptionState
│   │   └── capability.py           # Capability, Extension (value obj)
│   │
│   ├── entities/                    # EXISTING — kept, entities within aggregates
│   │   ├── __init__.py
│   │   ├── order.py                # Order, OrderResponse
│   │   ├── trade.py                # Trade
│   │   ├── position.py             # Position, Holding
│   │   ├── account.py              # Balance, FundLimits
│   │   ├── alerts.py               # ConditionalAlert, PnlExitPolicy
│   │   └── options.py              # OptionChain, FutureChain (data only)
│   │
│   ├── events/                      # EXISTING — kept
│   │   ├── __init__.py
│   │   ├── types.py                # DomainEvent, EventType, TypedEvents
│   │   └── handlers.py             # Event handler protocols
│   │
│   ├── ports/                       # EXISTING — restructured
│   │   ├── __init__.py
│   │   ├── providers.py            # NEW — DataProvider, ExecutionProvider
│   │   ├── repositories.py         # NEW — Repository protocols
│   │   ├── event_publisher.py      # EXISTING — kept
│   │   ├── observability.py        # EXISTING — kept
│   │   ├── risk_manager.py         # EXISTING — kept
│   │   └── broker_gateway.py       # EXISTING — kept (for backward compat)
│   │
│   ├── providers/                   # NEW — Provider Registry
│   │   ├── __init__.py
│   │   ├── registry.py             # ProviderRegistry
│   │   └── protocols.py            # DataProvider, ExecutionProvider
│   │
│   ├── extensions/                  # NEW — Extension Framework
│   │   ├── __init__.py
│   │   ├── base.py                 # Extension ABC
│   │   └── registry.py             # ExtensionRegistry
│   │
│   ├── services/                    # NEW — Domain Services
│   │   ├── __init__.py
│   │   ├── instrument_service.py   # Instrument lifecycle operations
│   │   ├── market_data_service.py  # Market data aggregation
│   │   └── chain_service.py        # Option/Future chain operations
│   │
│   ├── repositories/                # NEW — Repository Protocols
│   │   ├── __init__.py
│   │   ├── instrument_repository.py
│   │   ├── order_repository.py
│   │   └── position_repository.py
│   │
│   ├── enums.py                     # EXISTING — kept
│   ├── types.py                     # EXISTING — kept
│   ├── requests.py                  # EXISTING — kept
│   ├── market_enums.py              # EXISTING — kept
│   ├── instrument_id.py             # EXISTING — kept (backwards compat re-export)
│   ├── symbols.py                   # EXISTING — kept
│   ├── capabilities.py              # DEPRECATED — replaced by Extension system
│   ├── correlation.py               # EXISTING — kept
│   ├── provenance.py                # EXISTING — kept
│   └── ...
│
├── application/                     # USE CASES
│   ├── __init__.py
│   │
│   ├── trading/                     # EXISTING — kept
│   │   ├── execution_service.py
│   │   └── models.py
│   │
│   ├── oms/                         # EXISTING — kept
│   │   ├── order_manager.py
│   │   ├── risk_manager.py
│   │   ├── position_manager.py
│   │   ├── context.py
│   │   ├── protocols.py
│   │   └── ...
│   │
│   ├── market_data/                 # NEW — Market Data Use Cases
│   │   ├── __init__.py
│   │   ├── get_quote.py            # Use case: fetch latest quote
│   │   ├── get_history.py          # Use case: fetch historical data
│   │   ├── get_depth.py            # Use case: fetch market depth
│   │   ├── subscribe.py            # Use case: subscribe to live feed
│   │   └── get_option_chain.py     # Use case: fetch option chain
│   │
│   └── instrument/                  # NEW — Instrument Use Cases
│       ├── __init__.py
│       ├── discover.py             # Use case: discover instruments
│       ├── resolve.py              # Use case: resolve symbol to instrument
│       └── get_capabilities.py     # Use case: query instrument capabilities
│
├── infrastructure/                  # TECHNICAL IMPLEMENTATIONS
│   ├── __init__.py
│   │
│   ├── providers/                   # NEW — Concrete Providers
│   │   ├── __init__.py
│   │   ├── broker/                  # BrokerDataProvider, BrokerExecutionProvider
│   │   ├── csv/                     # CsvDataProvider
│   │   ├── replay/                  # ReplayDataProvider
│   │   ├── cache/                   # CacheDataProvider (decorator)
│   │   ├── composite/              # CompositeDataProvider (fallback chain)
│   │   └── dataframe/              # DataFrameDataProvider (tests)
│   │
│   ├── extensions/                  # NEW — Concrete Extensions
│   │   ├── __init__.py
│   │   ├── dhan/                   # Dhan-specific extensions
│   │   │   ├── depth200.py
│   │   │   ├── forever_orders.py
│   │   │   ├── super_orders.py
│   │   │   └── native_slice.py
│   │   └── upstox/                 # Upstox-specific extensions
│   │       ├── advanced_quotes.py
│   │       └── extended_feed.py
│   │
│   ├── repositories/                # NEW — Repository Implementations
│   │   ├── __init__.py
│   │   ├── in_memory/              # In-memory (testing)
│   │   └── duckdb/                 # DuckDB (production)
│   │
│   ├── event_bus/                   # EXISTING — kept
│   ├── lifecycle/                   # EXISTING — kept
│   ├── cache.py                     # EXISTING — kept
│   └── ...
│
├── analytics/                       # EXISTING — enhanced
│   ├── __init__.py                  # Enhanced with instrument-aware methods
│   ├── core/
│   │   ├── providers.py             # EXISTING — kept (adapter to DataProvider)
│   │   ├── instrument_analyzer.py   # NEW — Instrument-aware analytics facade
│   │   └── ...
│   └── ...
│
├── brokers/                         # EXISTING — kept (adapter layer)
│   ├── common/
│   ├── dhan/
│   └── upstox/
│
├── datalake/                        # EXISTING — kept
├── cli/                             # EXISTING — kept
├── api/                             # EXISTING — kept
└── config/                          # EXISTING — kept
```

### 8.2 Dependency Rules

```
ALLOWED IMPORTS (strictly enforced):

domain/
  ← imports NOTHING from infrastructure, brokers, application, analytics, cli

application/
  ← imports domain.*
  ← imports NOTHING from infrastructure, brokers, analytics, cli

infrastructure/
  ← imports domain.*
  ← imports NOTHING from brokers, analytics, cli

analytics/
  ← imports domain.*
  ← imports NOTHING from brokers, infrastructure, cli

brokers/
  ← imports domain.*
  ← imports NOTHING from analytics, cli

cli/
  ← imports domain.*, application.*, analytics.*, infrastructure.*, brokers.*
```

---

## 9. Public API Design

### 9.1 Current vs Proposed API

#### Current: Scattered, service-oriented

```python
# Need to know which service to call for each operation
from brokers.dhan import DhanConnection
from datalake.adapters.analytics_provider import DataLakeMarketDataProvider
from analytics import Analytics

conn = DhanConnection()
gateway = conn.gateway

# Market data — know which gateway method to call
quote = gateway.ltp("RELIANCE", "NSE")
history = gateway.history("RELIANCE", timeframe="1D", lookback_days=120)
depth = gateway.depth("RELIANCE", "NSE")

# Analytics — need separate provider
provider = DataLakeMarketDataProvider()
analytics = Analytics.from_provider(provider)
result = analytics.stock("RELIANCE", prices_df)

# Orders — know the gateway method
from domain import OrderRequest, Side, OrderType
order = OrderRequest(symbol="RELIANCE", exchange="NSE", side=Side.BUY,
                     quantity=10, order_type=OrderType.MARKET)
response = gateway.place_order(order)
```

#### Proposed: Instrument-centric, unified

```python
# Single entry point: ProviderRegistry
from domain.providers import ProviderRegistry
from domain.extensions import ExtensionRegistry
from domain import InstrumentId

# Composition root (once, at startup)
registry = ProviderRegistry()
registry.register_data_provider("broker", BrokerDataProvider(dhan_gateway))
registry.register_data_provider("csv", CsvDataProvider("data/"))
registry.register_data_provider("replay", ReplayDataProvider())

extensions = ExtensionRegistry()
extensions.register(Depth200Extension(dhan_client))
extensions.register(ForeverOrderExtension(dhan_client))

# Get instrument — everything flows from here
instrument_id = InstrumentId.equity("NSE", "RELIANCE")
instrument = InstrumentAggregate(
    instrument_id=instrument_id,
    data_provider=registry.get_data_provider(),
    extensions=extensions.available_for(instrument_id),
)

# Market data — natural, instrument-centric
quote = instrument.get_quote()                    # → QuoteSnapshot
history = instrument.get_history(timeframe="1D")  # → pd.DataFrame
depth = instrument.get_depth()                    # → MarketDepth

# Live subscription
subscription = instrument.subscribe(on_tick=my_callback)

# Check capabilities
if instrument.has_extension("depth200"):
    deep_depth = await instrument.get_extension("depth200").get_depth_200()

# Analytics — instrument-aware
from analytics.core.instrument_analyzer import InstrumentAnalyzer
analyzer = InstrumentAnalyzer(provider=registry.get_data_provider())
result = analyzer.analyze_stock(instrument, lookback_days=120)

# Orders — still through execution provider
exec_provider = registry.get_execution_provider()
order = OrderRequest(
    instrument_id=instrument_id,
    side=Side.BUY,
    quantity=10,
    order_type=OrderType.MARKET,
)
result = exec_provider.place_order(order)
```

### 9.2 Notebook / REPL API

```python
# Simple entry point for data scientists
from domain import InstrumentId
from domain.providers import ProviderRegistry

# Auto-configure from data lake
registry = ProviderRegistry.from_datalake(root="data/")

# Direct instrument access
nifty = InstrumentId.option("NFO", "NIFTY", date(2026, 7, 30), 25000, "CE")
instrument = registry.instrument(nifty)

# All data through instrument
df = instrument.get_history(timeframe="5m", lookback_days=30)
chain = instrument.option_chain()
greeks = chain.atm().greeks

# Analytics integration
from analytics import Analytics
analytics = Analytics(provider=registry.get_data_provider())
result = analytics.analyze(instrument)
```

---

## 10. Internal Architecture

### 10.1 Instrument Lifecycle Service

```python
# ── domain/services/instrument_service.py ──────────────────────────

class InstrumentService:
    """Domain service for instrument lifecycle management.
    
    Responsibilities:
    - Discover instruments from broker catalogs
    - Resolve symbols to InstrumentIds
    - Create InstrumentAggregate instances
    - Manage subscription lifecycle
    """
    
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        extension_registry: ExtensionRegistry,
        instrument_repository: InstrumentRepository,
    ) -> None:
        self._providers = provider_registry
        self._extensions = extension_registry
        self._repository = instrument_repository
    
    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentAggregate:
        """Resolve a symbol to an InstrumentAggregate.
        
        1. Check if instrument exists in repository
        2. If not, resolve via provider
        3. Create aggregate with appropriate providers
        4. Attach available extensions
        """
        instrument_id = InstrumentId.equity(exchange, symbol)
        return self._create_aggregate(instrument_id)
    
    def resolve_option(
        self,
        underlying: str,
        expiry: date,
        strike: Decimal,
        right: str,
        exchange: str = "NFO",
    ) -> InstrumentAggregate:
        """Resolve an option to an InstrumentAggregate."""
        instrument_id = InstrumentId.option(exchange, underlying, expiry, strike, right)
        return self._create_aggregate(instrument_id)
    
    def get_option_chain(
        self,
        underlying: str,
        expiry: date | None = None,
    ) -> OptionChainAggregate:
        """Get option chain as an aggregate."""
        chain_provider = self._providers.get_data_provider()
        chain = chain_provider.get_option_chain(
            InstrumentId.equity("NFO", underlying),
            expiry=expiry,
        )
        return OptionChainAggregate.from_chain(chain)
    
    def _create_aggregate(self, instrument_id: InstrumentId) -> InstrumentAggregate:
        """Create an InstrumentAggregate with the right providers."""
        data_provider = self._providers.get_data_provider()
        extensions = self._extensions.available_for(instrument_id)
        return InstrumentAggregate(
            instrument_id=instrument_id,
            data_provider=data_provider,
            extensions=extensions,
        )
```

### 10.2 InstrumentAggregate Implementation

```python
# ── domain/aggregates/instrument.py ────────────────────────────────

class InstrumentAggregate:
    """Instrument Aggregate Root — the central abstraction.
    
    Owns:
    - Identity (InstrumentId)
    - State (InstrumentState) — thread-safe internal mutation
    
    Delegates to:
    - DataProvider for market data
    - ExecutionProvider for trading
    - Extensions for broker-specific features
    
    Does NOT own:
    - Historical data storage (provider does)
    - Order management (OMS does)
    - Analytics computation (analytics engines do)
    """
    
    def __init__(
        self,
        instrument_id: InstrumentId,
        data_provider: DataProvider,
        execution_provider: ExecutionProvider | None = None,
        extensions: list[Extension] | None = None,
    ) -> None:
        self._id = instrument_id
        self._data_provider = data_provider
        self._execution_provider = execution_provider
        self._extensions = extensions or []
        self._state = InstrumentState()
        self._lock = threading.RLock()
    
    # ── Identity (read-only) ──────────────────────────────────────
    
    @property
    def id(self) -> InstrumentId:
        return self._id
    
    @property
    def symbol(self) -> str:
        return self._id.underlying
    
    @property
    def exchange(self) -> str:
        return self._id.exchange
    
    @property
    def asset_type(self) -> str:
        return self._id.asset_type
    
    # ── State (thread-safe read) ──────────────────────────────────
    
    @property
    def state(self) -> InstrumentState:
        with self._lock:
            return self._state
    
    @property
    def quote(self) -> QuoteSnapshot | None:
        return self.state.quote
    
    @property
    def depth(self) -> MarketDepth | None:
        return self.state.depth
    
    @property
    def is_subscribed(self) -> bool:
        return self.state.subscription.status == "SUBSCRIBED"
    
    # ── Data Operations (delegated to provider) ───────────────────
    
    def get_quote(self) -> QuoteSnapshot | None:
        """Fetch latest quote from provider and update state."""
        quote = self._data_provider.get_quote(self._id)
        if quote is not None:
            with self._lock:
                self._state = InstrumentState(
                    quote=quote,
                    depth=self._state.depth,
                    subscription=self._state.subscription,
                    last_update=datetime.now(timezone.utc),
                )
        return quote
    
    def get_history(
        self,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV from provider."""
        return self._data_provider.get_history(
            self._id,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )
    
    def get_depth(self) -> MarketDepth | None:
        """Fetch market depth from provider and update state."""
        depth = self._data_provider.get_depth(self._id)
        if depth is not None:
            with self._lock:
                self._state = InstrumentState(
                    quote=self._state.quote,
                    depth=depth,
                    subscription=self._state.subscription,
                    last_update=datetime.now(timezone.utc),
                )
        return depth
    
    # ── Subscription (delegated to provider) ──────────────────────
    
    def subscribe(
        self,
        callback: Callable[[InstrumentId, QuoteSnapshot], None],
        *,
        depth: bool = False,
    ) -> Subscription:
        """Subscribe to live market data."""
        with self._lock:
            self._state = InstrumentState(
                quote=self._state.quote,
                depth=self._state.depth,
                subscription=SubscriptionState(
                    status="SUBSCRIBING",
                    symbol=self.symbol,
                    exchange=self.exchange,
                ),
                last_update=self._state.last_update,
            )
        
        subscription = self._data_provider.subscribe(
            self._id,
            callback,
            depth=depth,
        )
        
        with self._lock:
            self._state = InstrumentState(
                quote=self._state.quote,
                depth=self._state.depth,
                subscription=SubscriptionState(
                    status="SUBSCRIBED",
                    symbol=self.symbol,
                    exchange=self.exchange,
                    started_at=datetime.now(timezone.utc),
                ),
                last_update=self._state.last_update,
            )
        
        return subscription
    
    # ── Extensions (composed, not inherited) ──────────────────────
    
    def has_extension(self, name: str) -> bool:
        """Check if this instrument has a named extension."""
        return any(ext.name == name for ext in self._extensions)
    
    def get_extension(self, name: str) -> Extension | None:
        """Get a named extension."""
        return next(
            (ext for ext in self._extensions if ext.name == name),
            None,
        )
    
    @property
    def extensions(self) -> list[Extension]:
        """All available extensions for this instrument."""
        return list(self._extensions)
    
    @property
    def capabilities(self) -> list[Capability]:
        """All capabilities from extensions."""
        caps = []
        for ext in self._extensions:
            caps.extend(ext.capabilities)
        return caps
    
    # ── Option Chain (delegated) ──────────────────────────────────
    
    def option_chain(self, expiry: date | None = None) -> OptionChain:
        """Get option chain for this instrument (must be an underlying)."""
        return self._data_provider.get_option_chain(self._id, expiry=expiry)
    
    def future_chain(self) -> FutureChain:
        """Get futures chain for this instrument (must be an underlying)."""
        return self._data_provider.get_future_chain(self._id)
    
    # ── Representation ────────────────────────────────────────────
    
    def __repr__(self) -> str:
        return (
            f"InstrumentAggregate({self._id}, "
            f"provider={self._data_provider.name}, "
            f"extensions={[e.name for e in self._extensions]})"
        )
```

### 10.3 Composition Root

```python
# ── composition_root.py (at application startup) ───────────────────

def build_registry(
    broker_name: str = "dhan",
    mode: str = "live",
    data_root: str = "data/",
) -> tuple[ProviderRegistry, ExtensionRegistry, InstrumentService]:
    """Build and wire all providers, extensions, and services.
    
    This is the ONLY place that knows about concrete implementations.
    Everything else depends on protocols.
    """
    
    # ── Providers ─────────────────────────────────────────────────
    provider_registry = ProviderRegistry()
    
    if mode == "live":
        # Import concrete broker (only here)
        from brokers.dhan import DhanConnection
        conn = DhanConnection()
        
        broker_data = BrokerDataProvider(conn.market_data, name="broker")
        provider_registry.register_data_provider("broker", broker_data)
        provider_registry.register_data_provider("default", broker_data)
        
        broker_exec = BrokerExecutionProvider(conn.orders, name="broker")
        provider_registry.register_execution_provider("broker", broker_exec)
        provider_registry.register_execution_provider("default", broker_exec)
    
    elif mode == "backtest":
        from infrastructure.providers.replay import ReplayDataProvider
        replay = ReplayDataProvider(root=data_root)
        provider_registry.register_data_provider("replay", replay)
        provider_registry.register_data_provider("default", replay)
    
    elif mode == "notebook":
        from infrastructure.providers.csv import CsvDataProvider
        csv = CsvDataProvider(path=data_root)
        provider_registry.register_data_provider("csv", csv)
        provider_registry.register_data_provider("default", csv)
    
    # ── Extensions ────────────────────────────────────────────────
    extension_registry = ExtensionRegistry()
    
    if broker_name == "dhan":
        from infrastructure.extensions.dhan.depth200 import Depth200Extension
        from infrastructure.extensions.dhan.forever_orders import ForeverOrderExtension
        extension_registry.register(Depth200Extension(conn.client))
        extension_registry.register(ForeverOrderExtension(conn.client))
    
    elif broker_name == "upstox":
        from infrastructure.extensions.upstox.advanced_quotes import AdvancedQuotesExtension
        extension_registry.register(AdvancedQuotesExtension(conn.client))
    
    # ── Services ──────────────────────────────────────────────────
    instrument_service = InstrumentService(
        provider_registry=provider_registry,
        extension_registry=extension_registry,
        instrument_repository=InMemoryInstrumentRepository(),
    )
    
    return provider_registry, extension_registry, instrument_service
```

---

## 11. Event Flow Redesign

### 11.1 Instrument Events

```python
# NEW event types for Instrument lifecycle

class EventType(str, Enum):
    # ... existing events ...
    
    # NEW: Instrument lifecycle events
    INSTRUMENT_DISCOVERED = "INSTRUMENT_DISCOVERED"
    INSTRUMENT_SUBSCRIBED = "INSTRUMENT_SUBSCRIBED"
    INSTRUMENT_UNSUBSCRIBED = "INSTRUMENT_UNSUBSCRIBED"
    INSTRUMENT_STATE_CHANGED = "INSTRUMENT_STATE_CHANGED"
    INSTRUMENT_ERROR = "INSTRUMENT_ERROR"
    
    # NEW: Provider events
    PROVIDER_CONNECTED = "PROVIDER_CONNECTED"
    PROVIDER_DISCONNECTED = "PROVIDER_DISCONNECTED"
    PROVIDER_FAILOVER = "PROVIDER_FAILOVER"
    
    # NEW: Extension events
    EXTENSION_REGISTERED = "EXTENSION_REGISTERED"
    EXTENSION_ACTIVATED = "EXTENSION_ACTIVATED"
```

### 11.2 Event Flow Diagrams

```
Instrument Subscription Flow:
═══════════════════════════════

  InstrumentService          InstrumentAggregate         DataProvider         EventBus
       │                            │                         │                  │
       │  resolve("RELIANCE")       │                         │                  │
       ├───────────────────────────▶│                         │                  │
       │                            │                         │                  │
       │                     create aggregate                 │                  │
       │                            │                         │                  │
       │  subscribe(callback)       │                         │                  │
       ├───────────────────────────▶│                         │                  │
       │                            │  subscribe(instrument_id, callback)       │
       │                            ├────────────────────────▶│                  │
       │                            │                         │                  │
       │                            │  INSTRUMENT_SUBSCRIBED  │                  │
       │                            ├─────────────────────────────────────────────▶
       │                            │                         │                  │
       │                            │  (ticks arrive)         │                  │
       │                            │◀────────────────────────┤                  │
       │                            │                         │                  │
       │                     update state                     │                  │
       │                     call callback                    │                  │
       │                     INSTRUMENT_STATE_CHANGED         │                  │
       │                            ├─────────────────────────────────────────────▶

Order Placement Flow (V2):
═══════════════════════════

  CLI / Strategy          InstrumentAggregate     ExecutionProvider       OMS
       │                        │                       │                  │
       │  instrument.buy(qty)   │                       │                  │
       ├───────────────────────▶│                       │                  │
       │                        │  place_order(request) │                  │
       │                        ├──────────────────────▶│                  │
       │                        │                       │  risk_check()    │
       │                        │                       ├─────────────────▶│
       │                        │                       │  approved/reject │
       │                        │                       │◀─────────────────┤
       │                        │  OrderResult          │                  │
       │                        │◀──────────────────────┤                  │
       │  result                │                       │                  │
       │◀───────────────────────┤                       │                  │
```

---

## 12. Testing Architecture

### 12.1 Testing Strategy

| Test Type | Scope | Tools | Gate |
|-----------|-------|-------|------|
| **Architecture Tests** | Import direction, aggregate boundaries | import-linter, custom pytest | CI |
| **Unit Tests** | Each aggregate, value object, service | pytest, hypothesis | CI |
| **Contract Tests** | Provider protocol conformance | pytest, runtime_checkable | CI |
| **Integration Tests** | Provider ↔ broker adapter | pytest, vcrpy | CI |
| **Extension Tests** | Extension registry, capability discovery | pytest | CI |
| **E2E Tests** | Full instrument lifecycle | pytest, test doubles | Pre-deploy |
| **Performance Tests** | Aggregate creation, provider lookup | pytest-benchmark | CI |
| **Thread Safety Tests** | Aggregate state mutations | threading, pytest | CI |

### 12.2 Test Doubles

```python
# ── tests/fixtures/fake_providers.py ───────────────────────────────

class FakeDataProvider:
    """In-memory data provider for testing."""
    
    def __init__(
        self,
        quotes: dict[str, QuoteSnapshot] | None = None,
        history: dict[str, pd.DataFrame] | None = None,
    ) -> None:
        self._quotes = quotes or {}
        self._history = history or {}
        self._subscriptions: list[tuple] = []
    
    @property
    def name(self) -> str:
        return "fake"
    
    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        return self._quotes.get(str(instrument_id))
    
    def get_history(self, instrument_id: InstrumentId, **kwargs) -> pd.DataFrame:
        return self._history.get(str(instrument_id), pd.DataFrame())
    
    # ... other methods


class FakeExecutionProvider:
    """In-memory execution provider for testing."""
    
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []
        self._order_counter = 0
    
    @property
    def name(self) -> str:
        return "fake"
    
    def place_order(self, request: OrderRequest) -> OrderResult:
        self._order_counter += 1
        order_id = f"FAKE-{self._order_counter}"
        self.orders.append(request)
        return OrderResult(success=True, order_id=order_id)
```

### 12.3 Contract Tests

```python
# ── tests/contract/test_provider_contracts.py ──────────────────────

class TestDataProviderContract:
    """Verify all DataProvider implementations satisfy the protocol."""
    
    @pytest.mark.parametrize(
        "provider_cls,fixture_name",
        [
            (FakeDataProvider, "fake_data"),
            (BrokerDataProvider, "broker_data"),
            (CsvDataProvider, "csv_data"),
        ],
    )
    def test_implements_protocol(self, provider_cls, fixture_name, request):
        provider = request.getfixturevalue(fixture_name)
        assert isinstance(provider, DataProvider)
    
    def test_get_quote_returns_none_or_snapshot(self, fake_data: FakeDataProvider):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        result = fake_data.get_quote(iid)
        assert result is None or isinstance(result, QuoteSnapshot)
    
    def test_get_history_returns_dataframe(self, fake_data: FakeDataProvider):
        iid = InstrumentId.equity("NSE", "RELIANCE")
        result = fake_data.get_history(iid)
        assert isinstance(result, pd.DataFrame)


class TestExtensionContract:
    """Verify all Extension implementations satisfy the protocol."""
    
    def test_extension_has_required_properties(self):
        ext = Depth200Extension(client=None)
        assert ext.name
        assert ext.broker
        assert ext.version
    
    def test_extension_is_available_for(self):
        ext = Depth200Extension(client=None)
        nse = InstrumentId.equity("NSE", "RELIANCE")
        mcx = InstrumentId.equity("MCX", "CRUDEOIL")
        assert ext.is_available_for(nse)
        assert not ext.is_available_for(mcx)
```

### 12.4 Thread Safety Tests

```python
# ── tests/threading/test_instrument_aggregate.py ───────────────────

class TestInstrumentAggregateConcurrency:
    """Verify InstrumentAggregate is thread-safe under concurrent access."""
    
    def test_concurrent_state_updates(self, instrument: InstrumentAggregate):
        """Multiple threads updating state should not corrupt it."""
        errors = []
        
        def update_state():
            try:
                for _ in range(100):
                    with instrument._lock:
                        instrument._state = InstrumentState(
                            quote=QuoteSnapshot(...),
                            subscription=instrument._state.subscription,
                        )
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=update_state) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert not errors
        assert instrument.quote is not None
```

---

## 13. Migration Plan

### 13.1 Migration Strategy

The migration follows a **strangler fig** pattern — new code uses V2 abstractions, old code continues working through adapters.

### 13.2 Phase Timeline

```
Phase 1 (Week 1-2): Foundation
├── Create domain/aggregates/instrument.py
├── Create domain/value_objects/ with state.py, capability.py, money.py
├── Create domain/providers/protocols.py
├── Create domain/extensions/base.py and registry.py
├── Unit tests for all new types
└── Architecture tests for package boundaries

Phase 2 (Week 3-4): Provider Framework
├── Implement ProviderRegistry
├── Create infrastructure/providers/broker/ (wraps existing adapters)
├── Create infrastructure/providers/csv/
├── Create infrastructure/providers/composite/
├── Create infrastructure/providers/dataframe/ (for tests)
├── Integration tests
└── Contract tests for all provider implementations

Phase 3 (Week 5): Extension Framework
├── Implement ExtensionRegistry
├── Port Depth200Extension from existing Dhan code
├── Port ForeverOrderExtension from existing Dhan code
├── Port AdvancedQuotesExtension from existing Upstox code
├── Extension contract tests
└── Capability discovery tests

Phase 4 (Week 6-7): InstrumentAggregate
├── Implement InstrumentAggregate
├── Implement InstrumentService
├── Wire up to ProviderRegistry and ExtensionRegistry
├── Create infrastructure/repositories/in_memory/
├── Instrument lifecycle tests
└── Thread safety tests

Phase 5 (Week 8): Analytics Integration
├── Create analytics/core/instrument_analyzer.py
├── Update Analytics facade to accept InstrumentAggregate
├── Adapter from DataProvider to MarketDataProvider (backward compat)
├── Analytics integration tests
└── E2E tests

Phase 6 (Week 9): Migration & Deprecation
├── Update CLI commands to use new API
├── Update API endpoints to use new API
├── Mark old interfaces as deprecated
├── Performance benchmarks
└── Documentation update
```

### 13.3 Backward Compatibility

During migration, adapters bridge old and new interfaces:

```python
# ── infrastructure/providers/adapter_to_old_interface.py ───────────

class DataProviderToMarketDataPort:
    """Adapter: DataProvider → MarketDataPort (for backward compatibility).
    
    Allows existing analytics code to work with the new Provider system
    without modification.
    """
    
    def __init__(self, provider: DataProvider) -> None:
        self._provider = provider
    
    def history(self, symbol: str, **kwargs) -> pd.DataFrame:
        instrument_id = InstrumentId.equity("NSE", symbol)
        return self._provider.get_history(instrument_id, **kwargs)
    
    def option_chain(self, underlying: str, **kwargs) -> OptionChain:
        instrument_id = InstrumentId.equity("NFO", underlying)
        return self._provider.get_option_chain(instrument_id, **kwargs)
    
    # ... etc
```

---

## 14. Decision Log

| ID | Decision | Date | Rationale |
|----|----------|------|-----------|
| D1 | Instrument as Aggregate Root | Jul 2026 | Central abstraction, every module works with instruments |
| D2 | Provider Registry over direct broker refs | Jul 2026 | Same instrument, multiple data sources; cleaner testing |
| D3 | Extension Registry over hardcoded capabilities | Jul 2026 | Runtime discovery, Open/Closed Principle |
| D4 | Composition over inheritance for Instrument | Jul 2026 | Prevents God Object; keeps Instrument thin |
| D5 | Value Objects for state snapshots | Jul 2026 | Immutability, thread safety, equality semantics |
| D6 | Strangler Fig migration | Jul 2026 | Zero-downtime migration; old code keeps working |
| D7 | Domain Services layer | Jul 2026 | Separates orchestration from entity state |
| D8 | Keep existing Event Bus | Jul 2026 | Already strong; extend with instrument events |
| D9 | Analytics integration via adapter | Jul 2026 | Backward compatibility during migration |
| D10 | Keep InstrumentId as-is | Jul 2026 | Already well-designed; no changes needed |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Aggregate Root** | The entry point to an aggregate; all external access goes through it |
| **Value Object** | An immutable object defined by its attributes, not identity |
| **Provider** | A data source or execution backend behind a protocol |
| **Extension** | A broker-specific capability registered at runtime |
| **Capability** | What an instrument/provider can do, discovered at runtime |
| **Instrument** | A tradeable financial instrument (equity, future, option, etc.) |
| **InstrumentId** | Canonical identity: exchange:underlying:expiry:strike:right |

## Appendix B: Comparison with Industry

| System | Central Abstraction | Our Design |
|--------|-------------------|------------|
| StockSharp | IConnector | InstrumentAggregate + Providers |
| Bloomberg | Security | InstrumentAggregate + Extensions |
| Interactive Brokers | Contract | InstrumentAggregate + Providers |
| QuantConnect | Symbol | InstrumentAggregate + Providers |
| MetaTrader | Symbol | InstrumentAggregate + Providers |

Our design follows the industry pattern: **instrument-centric with provider delegation**. The key innovation is the Extension system for broker-specific capabilities without polluting the domain model.
