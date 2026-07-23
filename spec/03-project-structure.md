# 03 — Project Structure

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2026-07-22  
**Related:** [02-Architecture](./02-architecture-overview.md), [04-Message Bus](./04-message-driven-architecture.md)

---

## 1. Overview

### Purpose

This document defines the complete project structure of the Vendeta framework — the organization of crates, modules, and their responsibilities. The structure enforces dependency rules and enables modular development.

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Clear boundaries** | Each crate has a single, well-defined responsibility |
| **Dependency direction** | Dependencies flow inward (adapters → gateway → core) |
| **Testability** | Each crate can be tested in isolation |
| **Extensibility** | New adapters/strategies don't modify core |
| **Build efficiency** | Minimal recompilation on changes |

---

## 2. Workspace Layout

```
vendeta/
├── Cargo.toml                    # Workspace root
├── Cargo.lock                    # Dependency lock file
├── Makefile                      # Build/test/run commands
├── Dockerfile                    # Container build
├── config/
│   └── example.yaml              # Configuration template
├── deploy/
│   └── vendeta.service           # systemd service file
├── docs/
│   └── architecture/             # Architecture documents
├── spec/                         # This specification set
├── crates/
│   ├── vendeta-core/             # Domain types (no I/O)
│   ├── vendeta-bus/              # Message bus + clock
│   ├── vendeta-gateway/          # Broker trait + capabilities
│   ├── vendeta-store/            # Persistence (SQLite + Parquet)
│   ├── vendeta-data/             # Market data infrastructure
│   ├── vendeta-engine/           # Processing engines
│   ├── vendeta-adapters/         # Broker implementations
│   │   ├── common/               # Shared adapter utilities
│   │   ├── dhan/                 # Dhan broker adapter
│   │   └── upstox/               # Upstox broker adapter
│   ├── vendeta-paper/            # Paper trading simulator
│   ├── vendeta-backtest/         # Backtest/replay engine
│   ├── vendeta-api/              # REST + WebSocket API
│   ├── vendeta-cli/              # Binary entry point
│   ├── vendeta-scanner/          # Market scanner
│   ├── vendeta-indicators/       # Technical indicators
│   ├── vendeta-config/           # Configuration loading
│   ├── vendeta-arch/             # Dependency rule tests
│   └── vendeta-py/               # Python bindings (PyO3)
└── .github/
    └── workflows/
        └── ci.yml                # CI/CD pipeline
```

---

## 3. Crate Specifications

### 3.1 vendeta-core

**Purpose:** Domain types, events, primitives. No I/O, no async, no external dependencies beyond serde/thiserror.

```
vendeta-core/
├── src/
│   ├── lib.rs                    # Public API
│   ├── primitives.rs             # Price, Quantity, Money, Timestamp, Symbol
│   ├── enums.rs                  # Side, OrderType, TimeInForce, Exchange, Segment
│   ├── events.rs                 # MarketEvent, OrderEvent
│   ├── errors.rs                 # Core error types
│   └── entities/
│       ├── mod.rs
│       ├── quote.rs              # Quote struct
│       ├── bar.rs                # Bar struct
│       ├── order.rs              # Order, OrderRequest
│       ├── position.rs           # Position struct
│       ├── signal.rs             # Signal struct
│       ├── instrument.rs         # Instrument, InstrumentId
│       ├── depth.rs              # Order book depth
│       ├── account.rs            # Account, Margin
│       └── timeframe.rs          # Timeframe enum
├── tests/
│   ├── primitives.rs
│   ├── entities.rs
│   ├── enums.rs
│   └── primitives_proptest.rs    # Property-based tests
└── Cargo.toml
```

**Dependencies:** `serde`, `thiserror`  
**Dependents:** All other crates

**Key Types:**

```rust
// Fixed-point price (i64, precision = 10_000)
pub struct Price(i64);

// Quantity (u64, no fractional shares in Indian equity)
pub struct Quantity(u64);

// Money (for P&L calculations)
pub struct Money(i64);

// Timestamp (nanoseconds since epoch)
pub struct Timestamp(i64);

// Symbol (interned string)
pub struct Symbol(Arc<str>);

// Instrument identifier
pub struct InstrumentId {
    pub symbol: Symbol,
    pub exchange: Exchange,
    pub segment: Segment,
}
```

---

### 3.2 vendeta-bus

**Purpose:** Message bus (broadcast + mpsc channels), Clock trait, global sequence numbering.

```
vendeta-bus/
├── src/
│   ├── lib.rs                    # Public API
│   ├── message_bus.rs            # MessageBus implementation
│   └── clock.rs                  # Clock trait, LiveClock, BacktestClock
├── tests/
│   └── message_bus.rs
└── Cargo.toml
```

**Dependencies:** `vendeta-core`, `tokio`  
**Dependents:** vendeta-data, vendeta-engine, vendeta-backtest

**Key Types:**

```rust
pub struct MessageBus {
    market_tx: broadcast::Sender<MarketEvent>,
    order_cmd_tx: mpsc::Sender<OrderCommand>,
    order_evt_tx: broadcast::Sender<OrderEvent>,
    sequence: AtomicU64,
}

pub trait Clock: Send + Sync {
    fn now_nanos(&self) -> i64;
    fn now(&self) -> Timestamp;
}

pub struct LiveClock;
pub struct BacktestClock { current: AtomicI64 }
```

---

### 3.3 vendeta-gateway

**Purpose:** BrokerGateway trait definition, capability model, contract tests.

```
vendeta-gateway/
├── src/
│   ├── lib.rs                    # BrokerGateway trait + types
│   ├── capabilities.rs           # BrokerCapabilities struct
│   ├── contract.rs               # Contract test utilities
│   └── instruments.rs            # Instrument resolution
├── tests/
│   └── object_safe.rs            # Verify trait is object-safe
└── Cargo.toml
```

**Dependencies:** `vendeta-core`, `async-trait`  
**Dependents:** vendeta-adapters, vendeta-engine, vendeta-data

**Key Types:**

```rust
#[async_trait]
pub trait BrokerGateway: Send + Sync {
    fn broker_id(&self) -> &str;
    fn capabilities(&self) -> &BrokerCapabilities;
    async fn authenticate(&self) -> GatewayResult<()>;
    async fn place_order(&self, request: &OrderRequest) -> GatewayResult<OrderId>;
    async fn cancel_order(&self, order_id: &OrderId) -> GatewayResult<()>;
    async fn modify_order(&self, order_id: &OrderId, request: &OrderRequest) -> GatewayResult<()>;
    async fn positions(&self) -> GatewayResult<Vec<Position>>;
    async fn holdings(&self) -> GatewayResult<Vec<Holding>>;
    async fn funds(&self) -> GatewayResult<Funds>;
    async fn ltp(&self, symbol: &Symbol) -> GatewayResult<Price>;
    async fn quote(&self, symbol: &Symbol) -> GatewayResult<Quote>;
    async fn history(&self, request: &HistoryRequest) -> GatewayResult<Vec<HistoricalBar>>;
    async fn option_chain(&self, symbol: &Symbol) -> GatewayResult<OptionChain>;
    // ... more methods
}

pub struct BrokerCapabilities {
    pub supports_options: bool,
    pub supports_futures: bool,
    pub supports_commodity: bool,
    pub supports_modify: bool,
    pub supports_oco: bool,
    pub max_order_size: u64,
    pub rate_limit_per_second: u32,
}
```

---

### 3.4 vendeta-store

**Purpose:** Persistence layer — SQLite for relational data, Parquet for time-series, event log for state reconstruction.

```
vendeta-store/
├── src/
│   ├── lib.rs                    # Public API
│   ├── errors.rs                 # Storage errors
│   ├── schema.rs                 # SQLite schema definitions
│   ├── event_log.rs              # Event sourcing log
│   ├── positions.rs              # Position persistence
│   └── parquet_cache.rs          # Parquet read/write
├── tests/
│   └── state_reconstruction.rs
└── Cargo.toml
```

**Dependencies:** `vendeta-core`, `rusqlite`, `arrow`, `parquet`  
**Dependents:** vendeta-backtest

---

### 3.5 vendeta-data

**Purpose:** Market data infrastructure — feed bridge, symbol manager, reconnection logic.

```
vendeta-data/
├── src/
│   ├── lib.rs                    # Public API
│   ├── feed_bridge.rs            # WebSocket → MessageBus
│   ├── symbol_manager.rs         # Subscription management
│   └── reconnect.rs              # Reconnection with backoff
└── Cargo.toml
```

**Dependencies:** `vendeta-core`, `vendeta-bus`, `vendeta-gateway`, `tokio-tungstenite`  
**Dependents:** vendeta-engine

---

### 3.6 vendeta-engine

**Purpose:** Core processing engines — DataEngine, ExecutionEngine, PortfolioEngine, RiskEngine, Strategy framework.

```
vendeta-engine/
├── src/
│   ├── lib.rs                    # Public API
│   ├── actor.rs                  # Actor model utilities
│   ├── trading_node.rs           # TradingNode composition root
│   ├── lifecycle.rs              # LifecycleManager, ManagedComponent
│   ├── data_engine.rs            # DataEngine (bar agg + strategy dispatch)
│   ├── execution_engine.rs       # ExecutionEngine (order lifecycle)
│   ├── order_manager.rs          # Order FSM, idempotency
│   ├── portfolio.rs              # PortfolioEngine (P&L, positions)
│   ├── risk_engine.rs            # RiskEngine (pre-trade checks)
│   ├── risk_controls.rs          # CircuitBreaker, KillSwitch, DailyLimits
│   ├── capital.rs                # CapitalAllocator
│   ├── strategy.rs               # Strategy trait
│   ├── strategy_context.rs       # StrategyContext (injected services)
│   ├── strategy_registry.rs      # StrategyRegistry
│   ├── bar_aggregator.rs         # Tick → Bar aggregation
│   ├── algorithms.rs             # TWAP, VWAP, Iceberg
│   └── post_trade.rs             # PostTradeMonitor
├── tests/
│   ├── paper_slice.rs
│   ├── risk_limits.rs
│   └── strategy_pipeline.rs
└── Cargo.toml
```

**Dependencies:** `vendeta-core`, `vendeta-bus`, `vendeta-gateway`  
**Dependents:** vendeta-api, vendeta-backtest, vendeta-cli

---

### 3.7 vendeta-adapters

**Purpose:** Broker-specific implementations of BrokerGateway.

```
vendeta-adapters/
├── common/                       # Shared adapter utilities
│   ├── src/
│   │   ├── lib.rs
│   │   ├── auth.rs               # Token management, TOTP
│   │   ├── http.rs               # HTTP client with retry
│   │   ├── capability_guard.rs   # Capability checking
│   │   ├── idempotency.rs        # Order deduplication
│   │   ├── instrument_keys.rs    # Symbol resolution
│   │   ├── normalize.rs          # DTO → domain conversion
│   │   ├── quota.rs              # Rate limiting
│   │   └── ...
│   └── Cargo.toml
├── dhan/                         # Dhan broker adapter
│   ├── src/
│   │   ├── lib.rs
│   │   ├── gateway.rs            # BrokerGateway impl
│   │   ├── auth.rs               # Dhan-specific auth
│   │   ├── streaming.rs          # WebSocket feed
│   │   ├── dto.rs                # Dhan JSON structures
│   │   ├── map.rs                # DTO → domain mapping
│   │   └── ...
│   ├── examples/
│   └── Cargo.toml
└── upstox/                       # Upstox broker adapter
    ├── src/
    │   ├── lib.rs
    │   ├── gateway.rs
    │   ├── auth.rs
    │   ├── streaming.rs
    │   ├── dto.rs
    │   └── ...
    └── Cargo.toml
```

**Dependencies:** `vendeta-gateway`, `vendeta-core`, `vendeta-adapters/common`  
**Dependents:** vendeta-cli

---

### 3.8 vendeta-paper

**Purpose:** Paper trading simulator — simulated fills, virtual portfolio.

```
vendeta-paper/
├── src/
│   ├── lib.rs
│   ├── oms.rs                    # Paper order management
│   ├── orders.rs                 # Paper order types
│   ├── portfolio.rs              # Virtual portfolio
│   ├── market_data.rs            # Simulated market data
│   └── sim_config.rs             # Simulation configuration
├── tests/
│   ├── contract.rs
│   └── fill_sim.rs
└── Cargo.toml
```

---

### 3.9 vendeta-backtest

**Purpose:** Replay engine — deterministic backtesting with historical data.

```
vendeta-backtest/
├── src/
│   ├── lib.rs
│   ├── config.rs                 # BacktestConfig
│   ├── replay.rs                 # ReplayEngine
│   ├── fill_sim.rs               # SimulatedFillSource
│   └── analytics.rs              # Performance metrics
└── Cargo.toml
```

---

### 3.10 vendeta-api

**Purpose:** REST + WebSocket API using Axum.

```
vendeta-api/
├── src/
│   ├── lib.rs
│   ├── rest.rs                   # REST endpoints
│   ├── ws.rs                     # WebSocket endpoints
│   ├── health.rs                 # Health check endpoint
│   ├── metrics.rs                # Prometheus metrics endpoint
│   └── state.rs                  # Shared application state
└── Cargo.toml
```

---

### 3.11 vendeta-cli

**Purpose:** Binary entry point — CLI commands.

```
vendeta-cli/
├── src/
│   └── main.rs                   # CLI entry point
└── Cargo.toml
```

---

### 3.12 vendeta-scanner

**Purpose:** Market scanner/screener.

```
vendeta-scanner/
├── src/
│   ├── lib.rs
│   ├── scanner.rs                # Scanner engine
│   ├── filter.rs                 # Filter DSL
│   └── universe.rs               # Universe management
└── Cargo.toml
```

---

### 3.13 vendeta-indicators

**Purpose:** Technical indicators (pure functions).

```
vendeta-indicators/
├── src/
│   ├── lib.rs
│   ├── trend.rs                  # SMA, EMA, WMA
│   ├── momentum.rs               # RSI, MACD, ROC
│   ├── volatility.rs             # ATR, Bollinger
│   └── volume.rs                 # OBV, VWAP
└── Cargo.toml
```

---

### 3.14 vendeta-config

**Purpose:** Configuration loading and validation.

```
vendeta-config/
├── src/
│   └── lib.rs                    # Config structs, YAML loading
└── Cargo.toml
```

---

### 3.15 vendeta-arch

**Purpose:** Dependency rule enforcement tests.

```
vendeta-arch/
├── src/
│   └── lib.rs
├── tests/
│   └── dependency_rules.rs       # Compile-time dependency checks
└── Cargo.toml
```

---

### 3.16 vendeta-py

**Purpose:** Python bindings via PyO3 (future).

```
vendeta-py/
├── src/
│   └── lib.rs                    # PyO3 module definition
└── Cargo.toml
```

---

## 4. Dependency Matrix

| Crate | core | bus | gateway | store | data | engine | adapters | backtest | api |
|-------|------|-----|---------|-------|------|--------|----------|----------|-----|
| **core** | — | | | | | | | | |
| **bus** | ✓ | — | | | | | | | |
| **gateway** | ✓ | | — | | | | | | |
| **store** | ✓ | | | — | | | | | |
| **data** | ✓ | ✓ | ✓ | | — | | | | |
| **engine** | ✓ | ✓ | ✓ | | | — | | | |
| **adapters** | ✓ | | ✓ | | | | — | | |
| **backtest** | ✓ | ✓ | | ✓ | | ✓ | | — | |
| **api** | ✓ | | | | | ✓ | | | — |
| **cli** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 5. Build Configuration

### Workspace Cargo.toml

```toml
[workspace]
resolver = "2"
members = [
    "crates/vendeta-core",
    "crates/vendeta-bus",
    "crates/vendeta-gateway",
    "crates/vendeta-store",
    "crates/vendeta-data",
    "crates/vendeta-engine",
    "crates/vendeta-adapters/common",
    "crates/vendeta-adapters/dhan",
    "crates/vendeta-adapters/upstox",
    "crates/vendeta-paper",
    "crates/vendeta-backtest",
    "crates/vendeta-api",
    "crates/vendeta-cli",
    "crates/vendeta-scanner",
    "crates/vendeta-indicators",
    "crates/vendeta-config",
    "crates/vendeta-arch",
    "crates/vendeta-py",
]

[workspace.package]
version = "0.1.0"
edition = "2021"
rust-version = "1.75"
license = "MIT"

[workspace.dependencies]
# Async runtime
tokio = { version = "1", features = ["full"] }
async-trait = "0.1"

# Serialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"
serde_yaml = "0.9"

# HTTP/WebSocket
reqwest = { version = "0.12", features = ["json"] }
tokio-tungstenite = "0.24"

# Web framework
axum = { version = "0.7", features = ["ws"] }

# Storage
rusqlite = { version = "0.32", features = ["bundled"] }
arrow = "53"
parquet = "53"

# Observability
tracing = "0.1"
tracing-subscriber = "0.3"
prometheus = "0.13"

# Python bindings
pyo3 = { version = "0.22", features = ["extension-module"] }

# Testing
proptest = "1"
criterion = "0.5"

[profile.release]
lto = "fat"
codegen-units = 1
panic = "abort"
strip = true
```

---

## 6. Module Organization Conventions

### File Naming

| Pattern | Purpose | Example |
|---------|---------|---------|
| `lib.rs` | Crate public API | Re-exports key types |
| `mod.rs` | Module definition | `entities/mod.rs` |
| `<noun>.rs` | Single concept | `quote.rs`, `order.rs` |
| `<noun>_manager.rs` | Stateful manager | `order_manager.rs` |
| `<noun>_engine.rs` | Processing engine | `execution_engine.rs` |
| `errors.rs` | Error types | Per-crate error enum |

### Visibility Rules

```rust
// lib.rs — public API
pub mod primitives;
pub mod entities;
pub mod events;

// Internal modules — crate-private
mod internal;
pub(crate) mod utils;
```

---

## 7. Testing Organization

### Test Types by Location

| Location | Type | Purpose |
|----------|------|---------|
| `src/*.rs` (`#[cfg(test)]`) | Unit | Test single functions/methods |
| `tests/*.rs` | Integration | Test crate public API |
| `tests/*_proptest.rs` | Property | Invariant testing |
| `crates/vendeta-arch/tests/` | Architecture | Dependency rules |

### Test Naming

```rust
#[test]
fn price_from_f64_rejects_nan() { }

#[test]
fn order_manager_transitions_to_filled_on_full_fill() { }

#[tokio::test]
async fn message_bus_delivers_to_all_subscribers() { }
```

---

## 8. Cross-References

- [02-Architecture Overview](./02-architecture-overview.md) — High-level design
- [04-Message Bus](./04-message-driven-architecture.md) — Bus implementation
- [08-Adapter System](./08-adapter-system.md) — Adapter crate details
- [17-Testing](./17-testing.md) — Testing strategy
