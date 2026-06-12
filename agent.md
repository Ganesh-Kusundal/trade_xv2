# TradeXV2 — Agent Onboarding Guide

## 1. What This Project Is

**TradeXV2** is a Python-based, production-grade algorithmic trading framework for Indian stock exchanges (NSE, BSE, MCX). It provides a broker-agnostic trading platform with:

- A **multi-broker adapter layer** (DhanHQ implemented; Upstox, ICICI, Paper planned)
- **Order Management System (OMS)** stubs
- **Event bus** for streaming market/signal/order/risk events
- **Portfolio tracking** (positions, holdings, funds)
- **Risk management** scaffolding
- **Strategy engine** scaffolding
- **Backtesting engine** scaffolding
- **Replay engine** scaffolding
- A **CLI/TUI diagnostic terminal** (using Rich + Textual)

The architecture is heavily inspired by a Java sibling project called **Trade_J**, and replicates its patterns (capability-based broker connections, SPI ports, token-bucket rate limiting, circuit breakers, retry with exponential backoff, GatewayResult monad, broker routing with fallback, etc.) in idiomatic Python.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Data Models | Pydantic v2 (legacy), dataclasses (canonical domain), pandas DataFrames (market data) |
| Broker SDK | `dhanhq` (DhanHQ official) |
| HTTP | `requests` |
| CLI/TUI | `rich`, `textual` |
| Data Processing | `pandas`, `polars` |
| Testing | `pytest`, `pytest-cov`, `pytest-asyncio` |
| Config | `.env` / `.env.local` files, environment variables |

---

## 3. Project Structure

```
Trade_XV2/
├── brokers/                  # Core broker module — the heart of the system
│   ├── common/               # Broker-agnostic abstractions
│   │   ├── api/              # SPI ports & provider registry
│   │   │   ├── ports.py      # Abstract capability contracts (OrderCommand, MarketDataProvider, etc.)
│   │   │   └── spi.py        # BrokerSource, BrokerDescriptor, BrokerProvider, BrokerRegistry
│   │   ├── contracts/        # Contract test suites & broker contract ABC
│   │   │   ├── broker_contract.py    # BrokerContractSuite (parameterized contract tests)
│   │   │   └── module_test_suite.py  # ModuleTestSuite runner (unit/contract/integration)
│   │   ├── core/             # Core domain types
│   │   │   ├── auth.py       # TokenSource, TokenState, TokenStateStore, AuthManager, TotpGenerator
│   │   │   ├── broker.py     # Abstract Broker ABC (canonical interface every adapter implements)
│   │   │   ├── connection.py # BrokerConnection ABC, Capability enum, ConnectionStatus
│   │   │   ├── domain.py     # Canonical dataclass models (Order, Position, Holding, Trade, etc.)
│   │   │   ├── enums.py      # ExchangeSegment, OrderType, ProductType, TransactionType, etc.
│   │   │   ├── instruments.py# Instrument dataclass, InstrumentRegistry
│   │   │   ├── models.py     # Pydantic models (legacy, still used by DhanBroker facade)
│   │   │   ├── result.py     # GatewayResult monad (success/failure with metadata)
│   │   │   └── schemas.py    # Canonical DataFrame schemas + builders + validation
│   │   └── resilience/       # Fault tolerance
│   │       ├── backoff.py    # NoBackoff, FixedBackoff, ExponentialBackoff (with jitter)
│   │       ├── circuit_breaker.py  # CircuitBreaker (CLOSED→OPEN→HALF_OPEN)
│   │       ├── errors.py     # BrokerError, RetryableError, NonRetryableError, etc.
│   │       ├── rate_limiter.py     # TokenBucketRateLimiter, MultiBucketRateLimiter
│   │       └── retry.py      # RetryExecutor (circuit breaker + rate limiter + backoff + retry)
│   ├── dhan/                 # DhanHQ broker adapter
│   │   ├── auth/             # Auth client, config, context, HTTP client, URL resolver
│   │   ├── mapper/           # Dhan↔canonical mapping (segments, instruments, symbols)
│   │   ├── market_data/      # Market data, options, portfolio, margin providers + adapters
│   │   ├── orders/           # Order command/query, validator, special orders (bracket, cover, GTT, slice)
│   │   ├── websocket/        # WebSocket market feed + order stream
│   │   ├── broker.py         # DhanBroker facade (1378 lines — the main integration point)
│   │   ├── client.py         # DhanClientHolder, TokenRotationListener
│   │   ├── exceptions.py     # DhanApiError
│   │   ├── alerts.py         # Alert scaffolding
│   │   └── risk.py           # Risk scaffolding
│   ├── handle.py             # BrokerHandle — fluent API wrapper around BrokerConnection
│   ├── router.py             # BrokerRouter — multi-broker routing with fallback
│   └── multiplexer.py        # WebSocketMultiplexer — subscription fan-out + WS client
├── cli/                      # CLI/TUI diagnostic terminal
│   ├── commands/             # Subcommand handlers (broker, account, portfolio, oms, market, etc.)
│   ├── diagnostics/          # Doctor command implementation
│   ├── load_testing/         # Load test harness
│   ├── services/             # Service layer (BrokerService, OmsService, EventBusService)
│   ├── views/                # TUI app (Textual-based dashboard)
│   ├── widgets/              # TUI widgets (broker, OMS, market, diagnostics, performance, events)
│   └── main.py               # Entry point — arg parsing → subcommand or TUI
├── oms/                      # Order Management System (placeholder)
├── event_bus/                # Event bus (placeholder)
├── portfolio/                # Portfolio manager (placeholder)
├── risk/                     # Risk management (placeholder)
├── strategy/                 # Strategy engine (placeholder)
├── backtesting/              # Backtesting engine (placeholder)
├── replay/                   # Replay engine (placeholder)
├── config/                   # Secret files (dhan-pin.txt, dhan-totp-secret.txt) — gitignored
├── runtime/                  # Runtime state (token JSON) — gitignored
├── tests/                    # Top-level test suites
│   ├── e2e/                  # End-to-end tests
│   ├── regression/           # Regression tests (placeholder)
│   ├── performance/          # Performance tests (placeholder)
│   └── run.py                # GlobalTestSuite runner
├── check_dhan.py             # Dhan connectivity diagnostic script
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest config (markers: unit, contract, dhan, integration, sandbox, live_readonly)
└── tradex                    # CLI entry point script
```

---

## 4. Architecture Overview

### 4.1 Two Model Systems

The project has **two parallel modeling layers** that coexist. Understanding this is critical:

#### Layer A: Pydantic Models (`brokers.common.core.models`)
- Legacy models used by the `DhanBroker` facade and its internal REST clients
- `OrderRequest`, `Order`, `Position`, `Holding`, `Trade`, `Quote`, `MarketDepth`, `FundLimits`, etc.
- Use Pydantic v2 `BaseModel`
- Referenced by the SPI ports in `api/ports.py`

#### Layer B: Canonical Domain Dataclasses (`brokers.common.core.domain`)
- Newer, broker-agnostic models that every adapter MUST return
- `Order`, `Position`, `Holding`, `Trade`, `FundLimits`, `OrderResponse` — all `@dataclass(slots=True)`
- Uses `Side` enum (not `TransactionType`)
- `OrderStatus.normalize()` maps broker-specific statuses → canonical statuses

#### Layer C: DataFrame Schemas (`brokers.common.core.schemas`)
- Market data is returned as **pandas DataFrames** with strict canonical schemas
- `HistoricalSchema`: OHLCV candles (timestamp, open, high, low, close, volume, oi, symbol, exchange, timeframe)
- `QuoteSchema`: Real-time quotes (symbol, exchange, ltp, bid, ask, volume, oi, timestamp)
- `OptionChainSchema`: Option chain with Greeks (16 columns including delta, gamma, theta, vega, rho)
- `MarketDepthSchema`: L2 depth with 20 bid/ask levels
- **Broker-specific columns** (`security_id`, `instrument_token`, `exchange_token`, `symbol_token`) are **forbidden** outside the adapter boundary
- Builder functions: `build_historical_df()`, `build_quote_df()`, `build_option_chain_df()`, `build_market_depth_df()`

### 4.2 The Abstract Broker Interface

Every broker adapter MUST implement `brokers.common.core.broker.Broker`:

```python
class Broker(ABC):
    name: str
    broker_id: str
    connect() -> bool
    disconnect() -> bool
    is_connected() -> bool
    get_historical_data(symbol, exchange, from_date, to_date, timeframe) -> DataFrame
    get_quote(symbol, exchange) -> DataFrame
    get_option_chain(underlying, exchange, expiry) -> DataFrame
    get_market_depth(symbol, exchange) -> DataFrame
    place_order(symbol, exchange, side, quantity, price, ...) -> OrderResponse
    get_order(order_id) -> Optional[Order]
    get_orders() -> List[Order]
    cancel_order(order_id) -> bool
    get_positions() -> List[Position]
    get_holdings() -> List[Holding]
    get_fund_limits() -> FundLimits
    get_trades() -> List[Trade]
```

### 4.3 Capability-Based Connection Pattern

`BrokerConnection` (in `core/connection.py`) provides capability discovery:

- `Capability` enum: MARKET_DATA, ORDER_COMMAND, ORDER_QUERY, PORTFOLIO, OPTIONS_CHAIN, INSTRUMENTS, FUTURES, HISTORICAL_DATA, WEBSOCKET, BRACKET_ORDER, COVER_ORDER, GTT_ORDER, SLICE_ORDER, MARGIN, SESSION_RISK, ALERTS, MARKET_STATUS, DEPTH, ORDER_STREAM, IDEMPOTENCY
- Subclasses register providers via `_register_capability(Capability.X, provider_instance)`
- Consumers discover at runtime: `conn.has_capability(Capability.MARKET_DATA)` → `conn.get_capability(Capability.MARKET_DATA)`

### 4.4 SPI Ports (`api/ports.py`)

Abstract contracts that adapters implement:

| Port | Responsibility |
|---|---|
| `OrderCommand` | place_order, modify_order, cancel_order, preview_order |
| `OrderQuery` | get_order, get_order_by_correlation_id, get_order_list, get_trades |
| `MarketDataProvider` | get_quote, get_historical_daily, get_historical_intraday, get_depth, get_option_chain |
| `PortfolioProvider` | get_positions, get_holdings, get_fund_limits, get_profile, get_ledger |
| `OptionsProvider` | get_expiries, get_option_chain |
| `MarginProvider` | calculate_margin |
| `InstrumentResolver` | is_loaded, register, load_catalog, lookup, require |
| `FuturesProvider` | get_contracts, get_nearest_contract, get_expiries, is_commodity |
| `BracketOrderProvider` | place/modify/cancel/get super orders |
| `CoverOrderProvider` | place/exit cover orders |
| `GttOrderProvider` | place/modify/cancel/get forever orders |
| `SliceOrderCommand` | place_slice_order |
| `SessionRiskProvider` | enable_pnl_exit |
| `ConditionalAlertProvider` | place/get/list/delete alerts |
| `MarketStatusProvider` | get_market_status |
| `IdempotencyCachePort` | get/put for duplicate order safety |

### 4.5 GatewayResult Monad

`GatewayResult[T]` wraps success/failure with metadata (source, latency, cache info):

```python
result = GatewayResult.success(data, metadata=meta)
result = GatewayResult.failure("error message")
result.map(transform).flat_map(more_work).recover(fallback)
```

### 4.6 Broker Routing

- `BrokerHandle`: Fluent wrapper around `BrokerConnection` with context manager support
- `BrokerRouter`: Routes operations across multiple handles with auto-fallback
  - `router.route(operation)` — tries default broker, falls back to others
  - `router.route_to("DHAN", operation)` — explicit broker selection

---

## 5. Dhan Adapter Deep Dive

### 5.1 DhanBroker Facade (`brokers/dhan/broker.py`)

The main class (~1378 lines) that ties everything together:

- **Construction**: `DhanBroker.from_env()` or `DhanBroker.from_properties()`
- **Init** wires up: settings → auth → HTTP client → URL resolver → instrument resolver → rate limiter → circuit breaker → retry executor → all adapter providers → capability registration
- **Dual interface**:
  - `*_rest` methods (e.g., `place_order_rest`, `get_market_quote_rest`) — thin wrappers around Dhan REST clients
  - Canonical `Broker` ABC methods (e.g., `place_order`, `get_quote`, `get_orders`) — normalize Dhan responses into canonical domain objects and DataFrames

### 5.2 Auth System (`brokers/dhan/auth/`)

- `DhanConnectionSettings`: Loaded from `.env` / `.env.local` via `DhanSettingsLoader`
- `DhanAuthClient`: Handles TOTP generation + token acquisition via Dhan's auth API
- `DhanTokenManager`: Token lifecycle (acquire, refresh, persist)
- Auth modes: `STATIC` (pre-configured token), `TOTP_GENERATED` (PIN + TOTP secret), `WEB_RENEWABLE` (bootstrap token)
- `DhanAuthenticatedHttpClient`: Attaches auth headers to all REST calls

### 5.3 Adapter Layer

Each Dhan capability has a two-part structure:
1. **Client** (raw REST calls): `DhanRestOrderClient`, `DhanMarketDataClient`, `DhanPortfolioClient`, `DhanOptionsClient`, `DhanMarginClient`
2. **Adapter** (implements SPI port): `DhanOrderCommandAdapter`, `DhanMarketDataProvider`, `DhanPortfolioProvider`, `DhanOptionsAdapter`, `DhanMarginProvider`, etc.

### 5.4 Mapper Layer (`brokers/dhan/mapper/`)

- `dhan_segment_mapper.py`: Maps `ExchangeSegment` ↔ Dhan segment strings
- `instruments.py`: `DhanInstrumentDefinition`, `DhanInstrumentResolver` (loads Dhan master CSV)
- `mapping.py`: Response field mapping (Dhan JSON → canonical models)
- `symbol_formatter.py`: Normalizes symbol strings

---

## 6. Resilience Patterns

Located in `brokers/common/resilience/`:

### 6.1 Rate Limiter
- `TokenBucketRateLimiter`: Thread-safe token bucket (refills at `rate_per_second`, bursts to `capacity`)
- `MultiBucketRateLimiter`: Multiple named buckets (e.g., "orders", "quotes", "data")

### 6.2 Circuit Breaker
- States: `CLOSED` → `OPEN` (after N failures) → `HALF_OPEN` (after timeout) → `CLOSED` (after N successes)
- Config: `failure_threshold`, `success_threshold`, `open_duration_ms`

### 6.3 Retry Executor
- Execution flow: Circuit Breaker Check → Rate Limit Acquire → Execute → Handle Result
- On `RetryableError`: backoff + retry (up to `max_attempts`)
- On `NonRetryableError`: immediate failure
- On `CircuitBreakerOpenError`: fast-fail

### 6.4 Backoff Strategies
- `NoBackoff`: Zero delay
- `FixedBackoff`: Constant delay
- `ExponentialBackoff`: `base * multiplier^attempt + jitter`, capped at `max_delay_ms`

---

## 7. CLI / TUI System

### 7.1 Entry Point
```bash
./tradex            # Launch TUI dashboard (Textual app)
./tradex <command>  # Run a subcommand
```

### 7.2 Architecture
- **Services** (`cli/services/`): `BrokerService`, `OmsService`, `EventBusService`
  - `BrokerService` resolves real DhanBroker (if `.env.local` exists) or falls back to `MockBroker`
  - Also registers mock `zerodha` and `upstox` brokers
- **Commands** (`cli/commands/`): Each subcommand is a module with a `run()` function
- **Views** (`cli/views/`): `TradexTuiApp` — Textual-based dashboard
- **Widgets** (`cli/widgets/`): Broker console, OMS console, market console, diagnostics, performance, events

### 7.3 Available Commands
```
broker, account, holdings, positions, orders, trades, oms,
quote, depth, option-chain, futures, historical, stream,
websocket, events, search, instrument, doctor, load-test
```

---

## 8. Testing Strategy

### 8.1 Test Locations
- **Module-owned tests**: `brokers/common/*/tests/`, `brokers/dhan/tests/`
- **Top-level tests**: `tests/e2e/`, `tests/regression/`, `tests/performance/`
- **CLI tests**: `cli/tests/`

### 8.2 Pytest Markers (defined in `pytest.ini`)
| Marker | Purpose |
|---|---|
| `unit` | Module-owned unit tests |
| `contract` | Broker/module contract tests |
| `dhan` | DhanHQ integration tests |
| `integration` | Tests calling external broker APIs |
| `sandbox` | Sandbox tests (may place/cancel orders) |
| `live_readonly` | Live read-only endpoint tests |

### 8.3 Contract Tests
`BrokerContractSuite` in `contracts/broker_contract.py` is a parameterized test suite that every broker adapter must pass:
- Verifies required capabilities (MARKET_DATA, ORDER_COMMAND, ORDER_QUERY, PORTFOLIO)
- Verifies required methods exist
- Validates DataFrame schemas (HistoricalSchema, QuoteSchema, OptionChainSchema, MarketDepthSchema)
- Validates domain objects have no broker-specific fields (no `security_id`, `instrument_token`, etc.)
- Tests order status normalization

### 8.4 Running Tests
```bash
# All tests
pytest

# Module-specific
python -m brokers.dhan.tests.run
python -m brokers.common.core.tests.run
python -m brokers.common.resilience.tests.run

# By marker
pytest -m unit
pytest -m contract
pytest -m "not integration and not sandbox and not live_readonly"

# Specific paths
pytest tests/e2e tests/regression tests/performance
```

---

## 9. Configuration & Secrets

### 9.1 Environment Variables (`.env` or `.env.local`)

```env
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=
DHAN_AUTH_MODE=STATIC          # STATIC | TOTP_GENERATED | WEB_RENEWABLE
DHAN_ENVIRONMENT=LIVE
DHAN_REST_BASE_URL=
DHAN_PIN=
DHAN_TOTP_SECRET=
DHAN_PIN_FILE=config/dhan-pin.txt
DHAN_TOTP_SECRET_FILE=config/dhan-totp-secret.txt
DHAN_TOKEN_STATE_FILE=runtime/dhan-token-state.json
DHAN_REFRESH_BUFFER_MINUTES=10
```

### 9.2 Secret Files (gitignored)
- `config/dhan-pin.txt` — Dhan PIN for TOTP auth
- `config/dhan-totp-secret.txt` — Base32 TOTP secret
- `runtime/dhan-token-state.json` — Persisted token state

### 9.3 .gitignore Coverage
- `.env`, `.env.local`, `.env.*` (except `.env.example`)
- `config/dhan-pin.txt`, `config/dhan-totp-secret.txt`
- `runtime/`, `runtime-dev/`

---

## 10. Coding Conventions

### 10.1 General
- Python 3.10+ with `from __future__ import annotations` at the top of most files
- Type hints everywhere (function signatures, class attributes)
- Docstrings on all public classes and methods (Google-style or module-level)
- `dataclasses` for canonical domain models, `pydantic.BaseModel` for legacy/API-facing models
- Enums extend `str, Enum` for JSON serialization

### 10.2 Imports
- Use fully qualified imports from package root: `from brokers.common.core.enums import ExchangeSegment`
- `__init__.py` files re-export the public API surface with `__all__`

### 10.3 Data Flow Rules
- **Broker-specific identifiers** (`security_id`, `instrument_token`) must NEVER leak past the adapter boundary
- Market data → canonical DataFrames (use builders from `schemas.py`)
- Trading data → canonical dataclasses from `domain.py`
- All broker-specific ↔ canonical translation happens in adapter classes

### 10.4 Error Handling
- `BrokerError` is the base exception
- `RetryableError` for transient failures (network timeout, 429, 503)
- `NonRetryableError` for permanent failures (invalid order, auth rejected)
- `GatewayResult` monad for wrapping operation outcomes

### 10.5 Section Dividers
Code uses Unicode box-drawing comment banners to organize sections:
```python
# ── Connection Lifecycle ─────────────────────────────────────
# ── Capability Discovery ──────────────────────────────────────
# ── Internal helpers ─────────────────────────────────────────
```

---

## 11. How To: Common Tasks

### 11.1 Add a New Broker Adapter

1. Create `brokers/<name>/` directory mirroring `brokers/dhan/` structure
2. Implement the `Broker` ABC from `brokers.common.core.broker`
3. Return canonical DataFrames for market data (use builders from `schemas.py`)
4. Return canonical dataclasses from `domain.py` for trading operations
5. Register capabilities in the `BrokerConnection._capability_map`
6. Implement adapter classes for each SPI port you support
7. Add a `BrokerProvider` in `spi.py` with a `BrokerDescriptor`
8. Register in `BrokerRegistry`
9. Add a `MockBroker` fallback in `BrokerService` for TUI testing
10. Create contract tests inheriting from `BrokerContractSuite`

### 11.2 Add a New Capability

1. Add to `Capability` enum in `core/connection.py`
2. Define the SPI port (abstract class) in `api/ports.py`
3. Implement in the adapter layer (`brokers/<name>/`)
4. Register via `_register_capability()` in the broker's `__init__`

### 11.3 Add a New CLI Command

1. Create `cli/commands/<name>.py` with a `run(args, service, console)` function
2. Add the subcommand routing in `cli/main.py`
3. If needed, add a service in `cli/services/`
4. If needed, add a widget in `cli/widgets/`

### 11.4 Add a New Schema (DataFrame)

1. Define columns in `brokers/common/core/schemas.py` as a `*Schema` class
2. Add a `build_*_df()` constructor function
3. Add validation via `validate()` classmethod
4. Add forbidden broker column check
5. Add contract test in `BrokerContractSuite`

---

## 12. Module Maturity Status

| Module | Status |
|---|---|
| `brokers/common/core/` | ✅ Production-ready |
| `brokers/common/api/` | ✅ Production-ready |
| `brokers/common/resilience/` | ✅ Production-ready |
| `brokers/common/contracts/` | ✅ Production-ready |
| `brokers/dhan/` | ✅ Production-ready (REST complete, WebSocket partial) |
| `brokers/handle.py` | ✅ Production-ready |
| `brokers/router.py` | ✅ Production-ready |
| `brokers/multiplexer.py` | ✅ Production-ready |
| `cli/` | ✅ Functional (TUI + all subcommands working) |
| `oms/` | 🟡 Placeholder (empty `__init__.py`) |
| `event_bus/` | 🟡 Placeholder (empty `__init__.py`) |
| `portfolio/` | 🟡 Placeholder (empty `__init__.py`) |
| `risk/` | 🟡 Placeholder (empty `__init__.py`) |
| `strategy/` | 🟡 Placeholder (only docstring) |
| `backtesting/` | 🟡 Placeholder (empty `__init__.py`) |
| `replay/` | 🟡 Placeholder (empty `__init__.py`) |
| `tests/regression/` | 🟡 Placeholder |
| `tests/performance/` | 🟡 Placeholder |

### Pending Dhan Features
- WebSocket market-feed parser (partial — client exists, parser incomplete)
- Order-stream WebSocket parser (partial)
- Reconnect controller and WebSocket health monitor
- 20-level market-depth parser/provider
- Idempotency cache for duplicate order placement safety
- News provider

---

## 13. Key Files Quick Reference

| File | Purpose |
|---|---|
| `brokers/__init__.py` | Top-level public API surface for the brokers module |
| `brokers/common/core/broker.py` | The `Broker` ABC — every adapter implements this |
| `brokers/common/core/domain.py` | Canonical domain dataclasses (Order, Position, etc.) |
| `brokers/common/core/schemas.py` | Canonical DataFrame schemas + builders + validation |
| `brokers/common/core/connection.py` | `BrokerConnection` ABC + `Capability` enum |
| `brokers/common/core/enums.py` | All trading enums |
| `brokers/common/core/result.py` | `GatewayResult` monad |
| `brokers/common/api/ports.py` | All SPI port contracts |
| `brokers/common/api/spi.py` | Broker registry, descriptors, provider factory |
| `brokers/dhan/broker.py` | DhanBroker facade (1378 lines) |
| `brokers/dhan/__init__.py` | Dhan adapter public API surface |
| `cli/main.py` | CLI entry point + subcommand routing |
| `cli/services/broker_service.py` | Broker resolution + MockBroker |
| `brokers/common/contracts/broker_contract.py` | Contract test suite |
| `pytest.ini` | Test markers and config |
| `requirements.txt` | Dependencies |

---

## 14. Safety Notes

- **Never run live orders** unless you understand the strategy, broker limits, and exchange rules
- `.env.local` with real credentials must NEVER be committed
- Dhan order placement validates before REST submission — validation errors block placement
- High-notional orders produce warnings unless strict validation is added
- Sandbox/live tests should only run with explicit user approval and safe credentials
- The `runtime/` directory stores token state and is gitignored
