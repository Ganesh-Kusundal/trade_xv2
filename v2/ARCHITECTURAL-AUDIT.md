# v2/ Architectural Audit — Shotgun Surgery & Coupling Defects

Scope: `v2/` only. Original `src/` is reference only.

---

## PHASE 1 — Codebase Mapping

### 1.1 Modules & Packages

| Directory | Responsibility | Key Files |
|---|---|---|
| `v2/src/domain/` | Core domain model: enums, value objects, entities, ports, commands | `enums.py` (106 lines, 16 StrEnums), `commands/__init__.py`, `ports/broker_adapter.py` |
| `v2/src/application/` | Use cases: OMS, risk management, reconciliation | `oms/`, `risk/`, `reconciliation/` |
| `v2/src/infrastructure/` | Cross-cutting: message bus, component lifecycle, clock, observability | `message_bus.py`, `component.py`, `clock.py`, `observability/` |
| `v2/src/plugins/brokers/` | Broker plugin system: 3 broker implementations + shared common | `dhan/` (11 files), `upstox/` (11 files), `paper/` (8 files), `common/` (10 files), `registry.py` |
| `v2/src/plugins/exchanges/` | Exchange-level utilities | `nse/calendar.py` |
| `v2/src/runtime/` | Execution engine, factory, discovery | `runtime.py`, `factory.py`, `broker_factory.py`, `execution_target.py` |
| `v2/src/datalake/` | Data catalog, source selection, quality | `catalog.py`, `source_selection.py`, `quality.py` |
| `v2/src/interface/` | User-facing: CLI, TUI, MCP, REST API | `cli.py`, `tui/app.py`, `mcp/server.py`, `api/` |
| `v2/src/config/` | Configuration loading and schema | `loader.py`, `schema.py` |
| `v2/src/shared/` | Shared utilities: env, errors, logging | `env.py`, `errors.py`, `logging/` |

### 1.2 Broker Plugin Architecture

```
Gateway (facade) → Connection (auth + transport + sub-adapters) → Adapters (orders, market_data, portfolio, instruments, streaming)
                    ↑
                 Wire (domain ↔ broker-native dict conversion)
                    ↑
               Common (transport, retry, circuit_breaker, rate_limit, ws_reconnect, constants)
```

- **3 broker implementations**: Dhan (live), Upstox (live), Paper (simulated)
- **Each broker has**: Gateway (1 file), Connection (1 file), Wire (1 file), Config (1 file), Auth (1 file), 5 Adapters (orders, market_data, portfolio, instruments, streaming), `__init__.py`
- **Shared common layer**: 10 files providing transport, resilience, constants, wire helpers

### 1.3 Import/Dependency Graph

```
domain.enums ──→ domain.commands ──→ domain.entities ──→ domain.value_objects
     ↑                 ↑                     ↑
     │                 │                     │
plugins.brokers.* ────┴─────────────────────┘
     │
     ├── common/ (constants, transport, retry, circuit_breaker, rate_limit, ws_reconnect, http_client, jwt_expiry, totp_cooldown, wire, wire_mapper, quote_normalize, capabilities, symbol_resolver)
     ├── dhan/ (gateway, connection, wire, config, auth, adapters/*)
     ├── upstox/ (gateway, connection, wire, config, auth, adapters/*)
     └── paper/ (gateway, connection, wire, adapters/*)
```

**Key dependency direction**: domain → plugins.brokers (NOT reverse). All broker modules import from `domain.*`.

### 1.4 Shared Constants, Types, Enums

| Constant/Value | Location(s) | Count |
|---|---|---|
| `"INR"` currency string | `dhan/wire.py` (4×), `upstox/wire.py` (4×), `dhan/adapters/instruments.py` (2×), `upstox/adapters/instruments.py` (1×) | 11 |
| `"NSE_EQ"` segment fallback | `dhan/wire.py`, `upstox/wire.py` | 2 |
| `"INTRADAY"` / `"I"` product type | `dhan/wire.py`, `upstox/wire.py` | 2 |
| `Decimal("0")` | `paper/adapters/orders.py`, `paper/adapters/portfolio.py`, `upstox/wire.py` | 3 |
| `Decimal("2")` mid-price divisor | `paper/adapters/market_data.py`, `paper/adapters/portfolio.py` | 2 |
| `Decimal("100")` fill price | `constants.py` (DEFAULT_FILL_PRICE), `paper/adapters/orders.py` | 2 |
| `Decimal("100")` bid/ask size | `paper/connection.py` | 1 |
| `TimeInForce.DAY` hard-coded | `dhan/wire.py`, `upstox/wire.py` | 2 |
| `30.0` HTTP timeout | `transport.py`, `upstox/auth.py` | 2 |
| `15.0` TOTP timeout | `dhan/auth.py` | 1 |
| `"TradeXV2/1.0"` User-Agent | `constants.py` (USER_AGENT), `dhan/adapters/instruments.py` | 2 |
| `_REPO_RUNTIME` path (parents[5]) | `dhan/config.py`, `upstox/config.py`, `totp_cooldown.py` | 3 |
| `_RUNTIME_DIR` path (parents[4]) | `dhan/adapters/instruments.py` | 1 |

### 1.5 Dead Code

| File | Description |
|---|---|
| `common/wire_mapper.py` | `WireMapper` dataclass — not imported by any adapter. DhanWire/UpstoxWire implement their own mapping. |
| `common/symbol_resolver.py` | `SymbolResolver` class — not imported by any adapter. DhanWire/UpstoxWire use module-level dicts. |

---

## PHASE 2 — Shotgun Surgery Detection

### [SMELL-1] Duplicated Gateway Facade Structure
**Pattern**: B (Duplicated logic) + F (Parallel inheritance)
**Files**: `dhan/gateway.py`, `upstox/gateway.py`, `paper/gateway.py`
**Symbol/Value**: Identical method signatures (get_quote, ltp, depth, history, place_order, submit_order, cancel_order, modify_order, get_order, get_orderbook, get_positions, get_holdings, get_funds, get_balance, load_instruments, search, stream, unstream, stream_order, mass_status, capabilities, connect, close, authenticate, disconnect)
**Blast Radius**: 3 files — adding any new broker method requires editing all 3 gateways
**Impact**: HIGH

### [SMELL-2] Duplicated Connection Class
**Pattern**: B (Duplicated logic) + F (Parallel inheritance)
**Files**: `dhan/connection.py`, `upstox/connection.py`
**Symbol/Value**: Identical `__init__` (config, wire, token_manager, limiter, transport setup, sub-adapter creation), `connect()`, `disconnect()`, `is_connected`, `load_instruments()`, `mass_status()`
**Blast Radius**: 2 files — adding any new connection-level concern requires editing both
**Impact**: HIGH

### [SMELL-3] Duplicated Streaming Adapter
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/streaming.py`, `upstox/adapters/streaming.py`
**Symbol/Value**: Identical `_ensure_ws()`, `_handle_ws_close()`, `_do_reconnect()`, `_replay_subscriptions()`, `_send_subscribe()`, `_send_order_subscribe()`, `stream()`, `unstream()`, `stream_order()`, `feed_raw()`, `close()`. Only WS message format differs.
**Blast Radius**: 2 files — adding reconnect logic requires editing both
**Impact**: HIGH

### [SMELL-4] Duplicated Orders Adapter
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/orders.py`, `upstox/adapters/orders.py`
**Symbol/Value**: Identical `place_order()`, `cancel_order()`, `modify_order()`, `get_order()`, `get_orderbook()`. Only API paths differ (`/orders` vs `/order/place`, etc.)
**Blast Radius**: 2 files — adding order logic requires editing both
**Impact**: HIGH

### [SMELL-5] Duplicated Market Data Adapter
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/market_data.py`, `upstox/adapters/market_data.py`
**Symbol/Value**: Identical `get_quote()`, `get_ltp()`, `get_depth()`, `get_history()`. Only API paths and response parsing differ.
**Blast Radius**: 2 files — adding market data logic requires editing both
**Impact**: HIGH

### [SMELL-6] Duplicated Portfolio Adapter
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/portfolio.py`, `upstox/adapters/portfolio.py`
**Symbol/Value**: Identical `get_positions()`, `get_holdings()`, `get_funds()`. Only API paths differ.
**Blast Radius**: 2 files
**Impact**: MEDIUM

### [SMELL-7] Duplicated Segment Mapping
**Pattern**: A (Scattered constants)
**Files**: `dhan/wire.py` (`_DHAN_SEGMENT`), `upstox/wire.py` (`_UPSTOX_SEGMENT`)
**Symbol/Value**: Identical dict `{"NSE": "NSE_EQ", "NFO": "NFO_FO", "MCX": "MCX_COMM", "BSE": "BSE_EQ"}`
**Blast Radius**: 2 files — adding a new exchange requires editing both
**Impact**: MEDIUM

### [SMELL-8] Duplicated Status Mapping
**Pattern**: A (Scattered constants) + B (Duplicated logic)
**Files**: `dhan/wire.py` (`_STATUS`), `upstox/wire.py` (`_STATUS`)
**Symbol/Value**: Overlapping status maps with different key casing (uppercase vs lowercase). Dhan has 10 entries, Upstox has 9 entries.
**Blast Radius**: 2 files — adding a new status requires editing both
**Impact**: MEDIUM

### [SMELL-9] Duplicated `_corr()` Function
**Pattern**: B (Duplicated logic)
**Files**: `dhan/wire.py`, `upstox/wire.py`
**Symbol/Value**: Identical correlation ID generation logic
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-10] Duplicated `to_position()` / `to_account()` Logic
**Pattern**: B (Duplicated logic)
**Files**: `dhan/wire.py`, `upstox/wire.py`
**Symbol/Value**: `to_position()` and `to_account()` have identical structure with different field names
**Blast Radius**: 2 files
**Impact**: MEDIUM

### [SMELL-11] Module-Level Mutable Dicts (Shared State)
**Pattern**: C (Cross-module state mutation)
**Files**: `dhan/wire.py` (`_SECURITY_IDS`), `upstox/wire.py` (`_INSTRUMENT_KEYS`)
**Symbol/Value**: Module-level dicts mutated by `register_security()`/`register_key()` and read by `security_id()`/`instrument_key()`
**Blast Radius**: 2 wire files + all tests that touch wire — tests flake when run in full suite because dicts persist across test runs
**Impact**: HIGH

### [SMELL-12] Hard-Coded "INR" Currency String
**Pattern**: A (Scattered constants)
**Files**: `dhan/wire.py` (4×), `upstox/wire.py` (4×), `dhan/adapters/instruments.py` (2×), `upstox/adapters/instruments.py` (1×)
**Symbol/Value**: `"INR"` string literal
**Blast Radius**: 4 files — changing currency requires editing all 4
**Impact**: MEDIUM

### [SMELL-13] Hard-Coded "INTRADAY"/"I" Product Type
**Pattern**: A (Scattered constants)
**Files**: `dhan/wire.py` (line 134: `command.product_type or "INTRADAY"`), `upstox/wire.py` (line 126: `command.product_type or "I"`)
**Symbol/Value**: Different default product types per broker
**Blast Radius**: 2 files
**Impact**: MEDIUM

### [SMELL-14] Hard-Coded "NSE_EQ" Fallback
**Pattern**: A (Scattered constants)
**Files**: `dhan/wire.py` (line 67), `upstox/wire.py` (line 58)
**Symbol/Value**: `"NSE_EQ"` fallback in `get_segment()`
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-15] Hard-Coded Account IDs
**Pattern**: A (Scattered constants)
**Files**: `dhan/wire.py` (line 191: `AccountId(value="dhan")`), `upstox/wire.py` (line 183: `AccountId(value="upstox")`), `paper/connection.py` (line 75: `AccountId(value="paper")`)
**Symbol/Value**: Broker-specific account ID strings
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-16] Hard-Coded API URLs
**Pattern**: A (Scattered constants)
**Files**: `dhan/config.py` (base_url, generate_token_url, ws_url), `upstox/config.py` (base_url, base_hft, token_url, ws_url), `dhan/adapters/instruments.py` (DHAN_INSTRUMENT_CSV, DHAN_MCX_COMM_URL)
**Symbol/Value**: Hard-coded URLs in config and instrument adapter
**Blast Radius**: 3 files
**Impact**: MEDIUM

### [SMELL-17] Hard-Coded Rate Limit Tables
**Pattern**: A (Scattered constants)
**Files**: `common/rate_limit.py` (DHAN_RATE_LIMITS, UPSTOX_RATE_LIMITS)
**Symbol/Value**: Rate limit configs with different values per bucket
**Blast Radius**: 1 file (but affects both connections)
**Impact**: MEDIUM

### [SMELL-18] Hard-Coded Timeout Values
**Pattern**: A (Scattered constants)
**Files**: `common/transport.py` (30.0), `dhan/auth.py` (15.0), `upstox/auth.py` (30.0)
**Symbol/Value**: Timeout seconds
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-19] Hard-Coded User-Agent Strings
**Pattern**: A (Scattered constants)
**Files**: `common/constants.py` (USER_AGENT), `dhan/adapters/instruments.py` (line 148: `"TradeXV2/1.0"`)
**Symbol/Value**: Different User-Agent strings
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-20] Hard-Coded Decimal Literals
**Pattern**: A (Scattered constants)
**Files**: `paper/adapters/orders.py` (Decimal("0")), `paper/adapters/portfolio.py` (Decimal("0")), `upstox/wire.py` (Decimal("0")), `paper/adapters/market_data.py` (Decimal("2")), `paper/adapters/portfolio.py` (Decimal("2")), `paper/connection.py` (Decimal("100"))
**Symbol/Value**: Decimal literals for zero, mid-price divisor, default size
**Blast Radius**: 4 files
**Impact**: LOW

### [SMELL-21] Hard-Coded TimeInForce.DAY
**Pattern**: A (Scattered constants)
**Files**: `dhan/wire.py` (line 166), `upstox/wire.py` (line 157), `wire_mapper.py` (line 70: `"DAY"`)
**Symbol/Value**: `TimeInForce.DAY` / `"DAY"` string
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-22] Frozen Dataclass Mutation Bug (Systemic)
**Pattern**: C (Cross-module state mutation) — mutation silently discarded
**Files**: `dhan/adapters/orders.py` (lines 38, 50), `upstox/adapters/orders.py` (lines 38, 50)
**Symbol/Value**: `order.transition_to(OrderStatus.SUBMITTED)` — return value NOT captured. Since Order is `@dataclass(frozen=True, slots=True)`, transition_to() returns a NEW instance. The original `order` is unchanged. The cache stores the un-transitioned order.
**Blast Radius**: 2 files + all tests that check order status after placement
**Impact**: HIGH

### [SMELL-23] Cross-Module State Mutation via Wire
**Pattern**: C (Cross-module state mutation)
**Files**: `dhan/adapters/instruments.py` (calls `self._wire.register_security()`), `upstox/adapters/instruments.py` (calls `self._wire.register_key()`), `dhan/wire.py` (mutates `_SECURITY_IDS`), `upstox/wire.py` (mutates `_INSTRUMENT_KEYS`)
**Symbol/Value**: Instrument adapters mutate wire's module-level dicts
**Blast Radius**: 4 files — wire dicts are shared mutable state
**Impact**: HIGH

### [SMELL-24] Transport Abstraction Bypass
**Pattern**: H (Law of Demeter violation)
**Files**: `dhan/connection.py` (lines 69-71: `getattr(self.transport, "_extra_headers", None)`), `dhan/adapters/instruments.py` (line 148: `urllib.request.Request` directly)
**Symbol/Value**: Connection reaches into transport internals; instrument adapter bypasses transport entirely
**Blast Radius**: 2 files
**Impact**: MEDIUM

### [SMELL-25] Duplicated authenticate() Error Handling
**Pattern**: B (Duplicated logic)
**Files**: `dhan/connection.py` (lines 65-94), `upstox/connection.py` (lines 58-85)
**Symbol/Value**: Identical try/except/force_refresh pattern with different error strings ("401"/"DH-901" vs "401"/"Unauthorized"/"UDAPI100050")
**Blast Radius**: 2 files — adding error handling requires editing both
**Impact**: MEDIUM

### [SMELL-26] Duplicated mass_status()
**Pattern**: B (Duplicated logic)
**Files**: `dhan/connection.py` (lines 108-113), `upstox/connection.py` (lines 99-104)
**Symbol/Value**: Identical method body
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-27] Duplicated connect/disconnect/is_connected
**Pattern**: B (Duplicated logic)
**Files**: `dhan/connection.py` (lines 62-63, 96-99, 101-103), `upstox/connection.py` (lines 55-56, 87-90, 92-94)
**Symbol/Value**: Identical connection lifecycle methods
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-28] Duplicated Capabilities
**Pattern**: A (Scattered constants)
**Files**: `dhan/gateway.py` (lines 19-25), `upstox/gateway.py` (lines 19-25)
**Symbol/Value**: Identical `BrokerCapabilities(supports_market_order=True, supports_limit_order=True, supports_stop_order=True, supports_modify=True, supports_cancel=True)`
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-29] Inconsistent Gateway Method Naming
**Pattern**: D (Implicit coupling via naming) + G (Inconsistent abstraction)
**Files**: `dhan/gateway.py` (uses `get_quote`, `ltp`, `depth`, `history`), `paper/gateway.py` (uses `get_quote`, `get_ltp`, `get_depth`, `get_history`), `upstox/gateway.py` (uses `get_quote`, `ltp`, `depth`, `history`)
**Symbol/Value**: Dhan/Upstox use `ltp()`/`depth()`/`history()`; Paper uses `get_ltp()`/`get_depth()`/`get_history()`
**Blast Radius**: 3 files — callers must know broker-specific method names
**Impact**: MEDIUM

### [SMELL-30] Inconsistent mass_status() Return Type
**Pattern**: G (Inconsistent abstraction)
**Files**: `paper/gateway.py` (returns `BrokerSnapshot`), `dhan/gateway.py` (returns `dict[str, Any]`), `upstox/gateway.py` (returns `dict[str, Any]`)
**Symbol/Value**: Paper returns typed snapshot; Dhan/Upstox return raw dict
**Blast Radius**: 3 files
**Impact**: MEDIUM

### [SMELL-31] Inconsistent get_balance() Presence
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/gateway.py` (has `get_balance()`), `upstox/gateway.py` (has `get_balance()`), `paper/gateway.py` (does NOT have `get_balance()`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-32] Inconsistent get_holdings() Presence
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/gateway.py` (has `get_holdings()`), `upstox/gateway.py` (has `get_holdings()`), `paper/gateway.py` (does NOT have `get_holdings()`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-33] Inconsistent authenticate() Presence
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/gateway.py` (has `authenticate()`), `upstox/gateway.py` (has `authenticate()`), `paper/gateway.py` (does NOT have `authenticate()`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-34] Inconsistent disconnect() Presence
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/gateway.py` (has `disconnect()`), `upstox/gateway.py` (has `disconnect()`), `paper/gateway.py` (does NOT have `disconnect()`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-35] Inconsistent Streaming feed_raw() Interface
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/adapters/streaming.py` (takes `payload: dict`), `upstox/adapters/streaming.py` (takes `payload: dict`), `paper/adapters/streaming.py` (takes `instrument_id: InstrumentId, quote: object`)
**Blast Radius**: 3 files — test helpers must know broker-specific interface
**Impact**: MEDIUM

### [SMELL-36] Inconsistent Streaming Callback Types
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/adapters/streaming.py` (`OnQuote = Callable[[Quote], None]`), `upstox/adapters/streaming.py` (`OnQuote = Callable[[Quote], None]`), `paper/adapters/streaming.py` (`Callback = Callable[..., None]`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-37] Inconsistent Streaming Subscription Storage
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/adapters/streaming.py` (`dict[str, OnQuote | None]`), `upstox/adapters/streaming.py` (`dict[str, OnQuote | None]`), `paper/adapters/streaming.py` (`list[InstrumentId]`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-38] Inconsistent Instrument Adapter Method Names
**Pattern**: D (Implicit coupling via naming)
**Files**: `dhan/adapters/instruments.py` (`load_instruments`, `search`, `resolve`), `upstox/adapters/instruments.py` (`load_instruments`, `search`), `paper/adapters/instruments.py` (`load`, `resolve`, `search`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-39] Inconsistent Instrument resolve() Error Handling
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/adapters/instruments.py` (returns `None`), `paper/adapters/instruments.py` (raises `KeyError`)
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-40] Inline Imports
**Pattern**: B (Duplicated logic) + poor practice
**Files**: `dhan/wire.py` (line 102: `from domain.entities import DepthLevel`), `dhan/adapters/market_data.py` (line 58: `from decimal import Decimal`), `paper/connection.py` (lines 51-53: `from datetime import datetime; from domain.entities import Quote; from domain.value_objects import Price, Quantity`)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-41] Fragile Path Calculations
**Pattern**: A (Scattered constants)
**Files**: `dhan/adapters/instruments.py` (`parents[4]`), `dhan/config.py` (`parents[5]`), `upstox/config.py` (`parents[5]`), `totp_cooldown.py` (`parents[5]`)
**Symbol/Value**: Different `parents[N]` indices for the same repo root
**Blast Radius**: 4 files — moving any file breaks the path
**Impact**: MEDIUM

### [SMELL-42] Hard-Coded Cache TTL/Cleanup Constants
**Pattern**: A (Scattered constants)
**Files**: `dhan/adapters/instruments.py` (`_INSTRUMENT_CACHE_TTL_HOURS = 6.0`, `_INSTRUMENT_CACHE_CLEANUP_DAYS = 7`)
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-43] Duplicated Instrument Type Mapping
**Pattern**: A (Scattered constants) + B (Duplicated logic)
**Files**: `dhan/adapters/instruments.py` (`_INSTRUMENT_TYPE_MAP`, `_SEGMENT_MAP`, `_OPTION_TYPE_MAP`), `upstox/adapters/instruments.py` (hardcodes `AssetClass.EQUITY`, `InstrumentType.EQUITY`)
**Symbol/Value**: Dhan has rich mapping; Upstox has none
**Blast Radius**: 2 files — adding instrument types requires editing Dhan only (Upstox silently misclassifies)
**Impact**: MEDIUM

### [SMELL-44] Upstox Instrument Master Uses Wrong Endpoint
**Pattern**: E (Fragmented feature ownership)
**Files**: `upstox/adapters/instruments.py` (line 23: `self._transport.get("/market-quote/quotes")`)
**Symbol/Value**: Uses quote endpoint for instrument master. Comment says "ponyail: master dump via CDN in prod" but no CDN path is implemented.
**Blast Radius**: 1 file
**Impact**: MEDIUM

### [SMELL-45] Dhan Instrument Adapter Bypasses Transport
**Pattern**: H (Law of Demeter violation)
**Files**: `dhan/adapters/instruments.py` (line 148: `urllib.request.Request` directly in `_download_csv()`)
**Symbol/Value**: CSV download bypasses HttpTransport, losing rate limiting, retry, circuit breaker
**Blast Radius**: 1 file
**Impact**: MEDIUM

### [SMELL-46] Duplicated _safe_float() Helper
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/instruments.py` (module-level function)
**Symbol/Value**: Could be in common utilities
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-47] Duplicated _to_instrument() vs _csv_row_to_instrument()
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/instruments.py` (lines 317-330 vs 165-219)
**Symbol/Value**: `_to_instrument()` is a simplified version of `_csv_row_to_instrument()` with less field parsing
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-48] PaperGateway Auto-Connects in __init__
**Pattern**: G (Inconsistent abstraction)
**Files**: `paper/gateway.py` (line 33: `self.connection.connect()`)
**Symbol/Value**: PaperGateway connects immediately on construction; Dhan/Upstox require explicit `connect()` call
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-49] PaperGateway.connect() Idempotency vs Dhan/Upstox
**Pattern**: G (Inconsistent abstraction)
**Files**: `paper/gateway.py` (lines 35-39: checks `is_connected`), `dhan/gateway.py` (line 41-42: no check), `upstox/gateway.py` (line 41-42: no check)
**Blast Radius**: 3 files
**Impact**: LOW

### [SMELL-50] PaperOrdersAdapter Correctly Captures transition_to() (Reference Pattern)
**Pattern**: B (Duplicated logic) — correct version
**Files**: `paper/adapters/orders.py` (lines 39, 42, 44, 57)
**Symbol/Value**: `order = order.transition_to(OrderStatus.SUBMITTED)` — correctly captures return value
**Blast Radius**: 2 files (Dhan/Upstox need to match this pattern)
**Impact**: HIGH (reference for fixing SMELL-22)

### [SMELL-51] DhanOrdersAdapter.get_order() Redundant Cache Check
**Pattern**: B (Duplicated logic) + poor control flow
**Files**: `dhan/adapters/orders.py` (lines 56-68)
**Symbol/Value**: `if order_id.value in self._cache:` branch does the same thing as the fallback — both call `self._transport.get()` and `self._wire.to_order()`
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-52] UpstoxOrdersAdapter.get_order() Redundant Cache Check
**Pattern**: B (Duplicated logic) + poor control flow
**Files**: `upstox/adapters/orders.py` (lines 57-73)
**Symbol/Value**: Same redundant pattern as Dhan
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-53] DhanOrdersAdapter.modify_order() Doesn't Update Cache
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/adapters/orders.py` (lines 52-54)
**Symbol/Value**: After modify, cache is not updated — stale order returned by get_order()
**Blast Radius**: 1 file
**Impact**: MEDIUM

### [SMELL-54] PaperOrdersAdapter.modify_order() Doesn't Transition State
**Pattern**: G (Inconsistent abstraction)
**Files**: `paper/adapters/orders.py` (lines 59-66)
**Symbol/Value**: Uses `replace()` to update price/quantity without state transition
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-55] DhanOrdersAdapter.cancel_order() Silent Cache Miss
**Pattern**: G (Inconsistent abstraction)
**Files**: `dhan/adapters/orders.py` (lines 42-50)
**Symbol/Value**: If order not in cache, does nothing silently. PaperOrdersAdapter raises KeyError.
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-56] Duplicated WS Message Construction
**Pattern**: B (Duplicated logic)
**Files**: `dhan/adapters/streaming.py` (lines 49-57 and 108-120), `upstox/adapters/streaming.py` (lines 43-44 and 94-101)
**Symbol/Value**: `stream()` and `_send_subscribe()` construct the same WS message
**Blast Radius**: 2 files
**Impact**: LOW

### [SMELL-57] Hard-Coded CSV URLs
**Pattern**: A (Scattered constants)
**Files**: `dhan/adapters/instruments.py` (lines 26-27)
**Symbol/Value**: `DHAN_INSTRUMENT_CSV`, `DHAN_MCX_COMM_URL`
**Blast Radius**: 1 file
**Impact**: MEDIUM

### [SMELL-58] Hard-Coded Cache Glob Pattern
**Pattern**: A (Scattered constants)
**Files**: `dhan/adapters/instruments.py` (line 336: `"dhan-instruments-*.csv"`)
**Blast Radius**: 1 file
**Impact**: LOW

### [SMELL-59] WireMapper is Dead Code
**Pattern**: B (Duplicated logic) — unused abstraction
**Files**: `common/wire_mapper.py`
**Symbol/Value**: `WireMapper` dataclass with `to_wire()`/`from_wire()` — not imported anywhere
**Blast Radius**: 1 dead file + 4 adapter files that could use it
**Impact**: MEDIUM

### [SMELL-60] SymbolResolver is Dead Code
**Pattern**: B (Duplicated logic) — unused abstraction
**Files**: `common/symbol_resolver.py`
**Symbol/Value**: `SymbolResolver` class — not imported anywhere
**Blast Radius**: 1 dead file + 2 wire files that could use it
**Impact**: MEDIUM

---

## PHASE 3 — Root Cause Classification

### 1. Missing shared vocabulary layer (constants, types, enums not centralized)
**Evidence**: SMELL-7, SMELL-8, SMELL-12, SMELL-13, SMELL-14, SMELL-15, SMELL-16, SMELL-17, SMELL-18, SMELL-19, SMELL-20, SMELL-21, SMELL-28, SMELL-41, SMELL-42, SMELL-43, SMELL-57, SMELL-58

The `common/constants.py` module exists but contains only 14 lines (7 constants). The vast majority of constants remain scattered across broker-specific files. Segment maps, status maps, rate limits, cache TTLs, API URLs, timeouts, Decimal literals, and account IDs are all duplicated or hardcoded.

### 2. Missing service / use-case layer (business logic leaking into I/O layers)
**Evidence**: SMELL-1, SMELL-2, SMELL-25, SMELL-26, SMELL-27, SMELL-44, SMELL-45

Gateway/Connection classes mix authentication, transport setup, sub-adapter orchestration, and business logic (mass_status, load_instruments). The instrument adapter bypasses the transport layer for CSV downloads. The Upstox instrument adapter uses a quote endpoint for instrument master data.

### 3. Missing domain model (raw dicts/primitives used instead of typed entities)
**Evidence**: SMELL-30, SMELL-35, SMELL-36, SMELL-37, SMELL-39, SMELL-44

`mass_status()` returns `dict[str, Any]` instead of `BrokerSnapshot` in Dhan/Upstox. `feed_raw()` takes raw dicts instead of typed payloads. Streaming callbacks use untyped `Callable[..., None]` in Paper. Instrument adapters return raw dicts from transport instead of typed responses.

### 4. Boundary violations (modules importing across layer boundaries)
**Evidence**: SMELL-24, SMELL-40, SMELL-45, SMELL-41

Connection reaches into transport internals (`_extra_headers`). Instrument adapter uses `urllib.request` directly, bypassing transport. Inline imports from `domain.entities` inside wire methods. Fragile `parents[N]` path calculations that cross directory boundaries.

### 5. Premature file splitting (one concept split across files without a unifying interface)
**Evidence**: SMELL-59, SMELL-60, SMELL-47, SMELL-10

`WireMapper` and `SymbolResolver` in common/ are dead code — they were extracted as abstractions but never integrated. Dhan has `_to_instrument()` and `_csv_row_to_instrument()` as two versions of the same logic. `to_position()` and `to_account()` are duplicated across wire files instead of being in a shared base.

### 6. Absent or inconsistent coding standards (naming, error handling, logging patterns differ per author/file)
**Evidence**: SMELL-29, SMELL-30, SMELL-31, SMELL-32, SMELL-33, SMELL-34, SMELL-35, SMELL-36, SMELL-37, SMELL-38, SMELL-39, SMELL-48, SMELL-49, SMELL-50, SMELL-51, SMELL-52, SMELL-53, SMELL-54, SMELL-55, SMELL-56

- Method naming: `get_quote`/`ltp`/`depth`/`history` (Dhan/Upstox) vs `get_quote`/`get_ltp`/`get_depth`/`get_history` (Paper)
- Return types: `BrokerSnapshot` (Paper) vs `dict[str, Any]` (Dhan/Upstox)
- Method presence: `get_balance()`, `get_holdings()`, `authenticate()`, `disconnect()` exist in Dhan/Upstox but not Paper
- Streaming interface: `feed_raw(dict)` (Dhan/Upstox) vs `feed_raw(InstrumentId, object)` (Paper)
- Callback types: `Callable[[Quote], None]` (Dhan/Upstox) vs `Callable[..., None]` (Paper)
- Subscription storage: `dict[str, OnQuote | None]` (Dhan/Upstox) vs `list[InstrumentId]` (Paper)
- Instrument adapter methods: `load_instruments` (Dhan/Upstox) vs `load` (Paper)
- resolve() error handling: returns `None` (Dhan) vs raises `KeyError` (Paper)
- Connection lifecycle: auto-connect in `__init__` (Paper) vs explicit `connect()` (Dhan/Upstox)
- connect() idempotency: checks `is_connected` (Paper) vs no check (Dhan/Upstox)
- transition_to() capture: correctly captured (Paper) vs discarded (Dhan/Upstox)
- get_order() control flow: redundant cache check (Dhan/Upstox)
- modify_order() cache update: not updated (Dhan) vs updated (Paper)
- cancel_order() error handling: silent skip (Dhan/Upstox) vs raises (Paper)

### 7. Frozen dataclass invariant violation (systemic)
**Evidence**: SMELL-22, SMELL-50

All v2/ entities use `@dataclass(frozen=True, slots=True)`. The `transition_to()` method returns a new instance via `dataclasses.replace()`. DhanOrdersAdapter and UpstoxOrdersAdapter discard the return value of `transition_to()`, making state transitions no-ops. PaperOrdersAdapter correctly captures the return value.

---

## PHASE 4 — Refactoring Plan

### REF-1: Extract shared broker vocabulary to common/
**Root Cause**: Missing shared vocabulary layer
**Action**: Extract
**From**: `dhan/wire.py` (`_DHAN_SEGMENT`), `upstox/wire.py` (`_UPSTOX_SEGMENT`), `dhan/wire.py` (`_STATUS`), `upstox/wire.py` (`_STATUS`), `dhan/adapters/instruments.py` (`_SEGMENT_MAP`, `_INSTRUMENT_TYPE_MAP`, `_OPTION_TYPE_MAP`), `common/rate_limit.py` (`DHAN_RATE_LIMITS`, `UPSTOX_RATE_LIMITS`), `dhan/config.py` (URLs), `upstox/config.py` (URLs), `dhan/adapters/instruments.py` (CSV URLs), `common/constants.py` (extend)
**To**: `common/broker_vocab.py` — shared segment maps, status maps, instrument type maps, rate limit tables, URL constants
**Touches**: `common/constants.py`, `common/broker_vocab.py` (new), `dhan/wire.py`, `upstox/wire.py`, `dhan/adapters/instruments.py`, `common/rate_limit.py`, `dhan/config.py`, `upstox/config.py`
**Test Strategy**: Unit tests for broker_vocab module; verify existing tests still pass
**Sequencing Note**: Must complete before REF-2, REF-3, REF-7

### REF-2: Fix frozen dataclass mutation bug
**Root Cause**: Frozen dataclass invariant violation
**Action**: Delete duplication (fix discarded return values)
**From**: `dhan/adapters/orders.py` (lines 38, 50), `upstox/adapters/orders.py` (lines 38, 50)
**To**: Capture `transition_to()` return value: `order = order.transition_to(OrderStatus.SUBMITTED)`
**Touches**: `dhan/adapters/orders.py`, `upstox/adapters/orders.py`
**Test Strategy**: Run existing order tests; verify order status is SUBMITTED after placement
**Sequencing Note**: Depends on REF-1 (for shared constants); must complete before REF-3

### REF-3: Introduce BaseBrokerConnection
**Root Cause**: Missing service/use-case layer + duplicated logic
**Action**: Introduce abstraction (extract common connection logic)
**From**: `dhan/connection.py`, `upstox/connection.py`
**To**: `common/base_connection.py` — `BaseBrokerConnection` with shared `connect()`, `disconnect()`, `is_connected`, `load_instruments()`, `mass_status()`, `authenticate()` template method
**Touches**: `common/base_connection.py` (new), `dhan/connection.py`, `upstox/connection.py`
**Test Strategy**: Integration tests for both connections; verify authentication flow unchanged
**Sequencing Note**: Depends on REF-1, REF-2

### REF-4: Introduce BaseBrokerGateway
**Root Cause**: Missing service/use-case layer + duplicated logic
**Action**: Introduce abstraction (extract common gateway logic)
**From**: `dhan/gateway.py`, `upstox/gateway.py`, `paper/gateway.py`
**To**: `common/base_gateway.py` — `BaseBrokerGateway` with standardized method names, return types, and presence
**Touches**: `common/base_gateway.py` (new), `dhan/gateway.py`, `upstox/gateway.py`, `paper/gateway.py`
**Test Strategy**: Verify all gateway methods work identically across brokers; integration tests
**Sequencing Note**: Depends on REF-3

### REF-5: Introduce BaseStreamingAdapter
**Root Cause**: Duplicated logic
**Action**: Introduce abstraction (extract common streaming logic)
**From**: `dhan/adapters/streaming.py`, `upstox/adapters/streaming.py`
**To**: `common/base_streaming.py` — `BaseStreamingAdapter` with shared `_ensure_ws()`, `_handle_ws_close()`, `_do_reconnect()`, `_replay_subscriptions()`, `close()`. Subclasses implement `_send_subscribe()` and `_ws_message()`.
**Touches**: `common/base_streaming.py` (new), `dhan/adapters/streaming.py`, `upstox/adapters/streaming.py`
**Test Strategy**: Verify reconnect and subscription replay work for both brokers
**Sequencing Note**: Depends on REF-1

### REF-6: Introduce BaseOrdersAdapter
**Root Cause**: Duplicated logic
**Action**: Introduce abstraction (extract common orders logic)
**From**: `dhan/adapters/orders.py`, `upstox/adapters/orders.py`
**To**: `common/base_orders.py` — `BaseOrdersAdapter` with shared `place_order()`, `cancel_order()`, `modify_order()`, `get_order()`, `get_orderbook()`. Subclasses implement `_place_order_path()`, `_cancel_order_path()`, etc.
**Touches**: `common/base_orders.py` (new), `dhan/adapters/orders.py`, `upstox/adapters/orders.py`
**Test Strategy**: Verify order placement, cancellation, modification work for both brokers
**Sequencing Note**: Depends on REF-2, REF-1

### REF-7: Introduce BaseMarketDataAdapter
**Root Cause**: Duplicated logic
**Action**: Introduce abstraction (extract common market data logic)
**From**: `dhan/adapters/market_data.py`, `upstox/adapters/market_data.py`
**To**: `common/base_market_data.py` — `BaseMarketDataAdapter` with shared `get_quote()`, `get_ltp()`, `get_depth()`, `get_history()`. Subclasses implement `_quote_path()`, `_ltp_path()`, etc.
**Touches**: `common/base_market_data.py` (new), `dhan/adapters/market_data.py`, `upstox/adapters/market_data.py`
**Test Strategy**: Verify market data retrieval works for both brokers
**Sequencing Note**: Depends on REF-1

### REF-8: Introduce BasePortfolioAdapter
**Root Cause**: Duplicated logic
**Action**: Introduce abstraction (extract common portfolio logic)
**From**: `dhan/adapters/portfolio.py`, `upstox/adapters/portfolio.py`
**To**: `common/base_portfolio.py` — `BasePortfolioAdapter` with shared `get_positions()`, `get_holdings()`, `get_funds()`
**Touches**: `common/base_portfolio.py` (new), `dhan/adapters/portfolio.py`, `upstox/adapters/portfolio.py`
**Test Strategy**: Verify portfolio retrieval works for both brokers
**Sequencing Note**: Depends on REF-1

### REF-9: Introduce BaseWireAdapter
**Root Cause**: Duplicated logic + missing domain model
**Action**: Introduce abstraction (extract common wire logic)
**From**: `dhan/wire.py`, `upstox/wire.py`
**To**: `common/base_wire.py` — `BaseBrokerWire` with shared `_corr()`, `to_position()`, `to_account()`, `get_segment()`, status mapping. Subclasses provide broker-specific field name maps.
**Touches**: `common/base_wire.py` (new), `dhan/wire.py`, `upstox/wire.py`, `common/wire.py` (merge)
**Test Strategy**: Verify wire conversion produces correct domain types for both brokers
**Sequencing Note**: Depends on REF-1

### REF-10: Eliminate module-level mutable dicts
**Root Cause**: Cross-module state mutation
**Action**: Delete duplication (replace with instance-level state)
**From**: `dhan/wire.py` (`_SECURITY_IDS`), `upstox/wire.py` (`_INSTRUMENT_KEYS`)
**To**: Instance-level dicts on `DhanWire`/`UpstoxWire` (or `BaseBrokerWire`)
**Touches**: `dhan/wire.py`, `upstox/wire.py`, `dhan/adapters/instruments.py`, `upstox/adapters/instruments.py`, `dhan/adapters/orders.py`, `upstox/adapters/orders.py`, `dhan/adapters/market_data.py`, `upstox/adapters/market_data.py`, `dhan/adapters/streaming.py`, `upstox/adapters/streaming.py`
**Test Strategy**: Run full test suite; verify no test flakiness from shared state
**Sequencing Note**: Depends on REF-9 (wire refactoring)

### REF-11: Standardize gateway method names and return types
**Root Cause**: Absent coding standards
**Action**: Enforce boundary (standardize interface)
**From**: `dhan/gateway.py` (`ltp`, `depth`, `history`), `paper/gateway.py` (`get_ltp`, `get_depth`, `get_history`), `dhan/gateway.py` (`mass_status` → `dict`), `paper/gateway.py` (`mass_status` → `BrokerSnapshot`)
**To**: All gateways use `get_quote`, `get_ltp`, `get_depth`, `get_history`, `mass_status` → `BrokerSnapshot`
**Touches**: `dhan/gateway.py`, `upstox/gateway.py`, `paper/gateway.py`, all callers
**Test Strategy**: Verify all callers work with standardized names
**Sequencing Note**: Depends on REF-4

### REF-12: Standardize streaming adapter interface
**Root Cause**: Absent coding standards
**Action**: Enforce boundary (standardize interface)
**From**: `dhan/adapters/streaming.py` (`feed_raw(dict)`), `paper/adapters/streaming.py` (`feed_raw(InstrumentId, object)`)
**To**: All streaming adapters use `feed_raw(payload: dict[str, Any])` with consistent callback types
**Touches**: `dhan/adapters/streaming.py`, `upstox/adapters/streaming.py`, `paper/adapters/streaming.py`, all tests
**Test Strategy**: Verify test helpers work with standardized interface
**Sequencing Note**: Depends on REF-5

### REF-13: Delete dead code
**Root Cause**: Premature file splitting
**Action**: Delete duplication
**From**: `common/wire_mapper.py`, `common/symbol_resolver.py`, `dhan/adapters/instruments.py` (`_to_instrument()`)
**To**: Remove unused files and methods
**Touches**: `common/wire_mapper.py` (delete), `common/symbol_resolver.py` (delete), `dhan/adapters/instruments.py` (remove `_to_instrument()`)
**Test Strategy**: Verify no imports break
**Sequencing Note**: Can be done independently

### REF-14: Fix instrument adapter bypass and endpoint issues
**Root Cause**: Missing service/use-case layer + boundary violations
**Action**: Enforce boundary
**From**: `dhan/adapters/instruments.py` (`urllib.request` direct), `upstox/adapters/instruments.py` (wrong endpoint)
**To**: Use transport for CSV download; use correct instrument master endpoint for Upstox
**Touches**: `dhan/adapters/instruments.py`, `upstox/adapters/instruments.py`
**Test Strategy**: Verify instrument loading works with transport injection
**Sequencing Note**: Depends on REF-1

### REF-15: Fix fragile path calculations
**Root Cause**: Boundary violations
**Action**: Extract
**From**: `dhan/adapters/instruments.py` (`parents[4]`), `dhan/config.py` (`parents[5]`), `upstox/config.py` (`parents[5]`), `totp_cooldown.py` (`parents[5]`)
**To**: Use a single `repo_root()` function in `common/paths.py`
**Touches**: `common/paths.py` (new), `dhan/adapters/instruments.py`, `dhan/config.py`, `upstox/config.py`, `totp_cooldown.py`
**Test Strategy**: Verify path resolution works from any file location
**Sequencing Note**: Independent

### REF-16: Standardize instrument adapter interface
**Root Cause**: Absent coding standards
**Action**: Enforce boundary
**From**: `dhan/adapters/instruments.py` (`load_instruments`, `resolve` → `None`), `paper/adapters/instruments.py` (`load`, `resolve` → `KeyError`)
**To**: All instrument adapters use `load_instruments()`, `resolve()` → `Instrument | None`, `search()`
**Touches**: `dhan/adapters/instruments.py`, `upstox/adapters/instruments.py`, `paper/adapters/instruments.py`, all callers
**Test Strategy**: Verify instrument resolution works consistently
**Sequencing Note**: Depends on REF-14

---

## PHASE 5 — Structural Recommendations

### 5.1 Proposed Directory Structure

```
v2/src/plugins/brokers/
├── __init__.py
├── registry.py                    # Plugin registration (unchanged)
├── common/
│   ├── __init__.py
│   ├── broker_vocab.py            # NEW: shared segment/status/instrument maps, rate limits, URLs
│   ├── base_connection.py         # NEW: BaseBrokerConnection
│   ├── base_gateway.py            # NEW: BaseBrokerGateway
│   ├── base_wire.py               # NEW: BaseBrokerWire (merges wire.py)
│   ├── base_orders.py             # NEW: BaseOrdersAdapter
│   ├── base_market_data.py        # NEW: BaseMarketDataAdapter
│   ├── base_portfolio.py          # NEW: BasePortfolioAdapter
│   ├── base_streaming.py          # NEW: BaseStreamingAdapter
│   ├── base_instruments.py        # NEW: BaseInstrumentAdapter
│   ├── constants.py               # Extended: all shared constants
│   ├── paths.py                   # NEW: repo_root() function
│   ├── transport.py               # Unchanged
│   ├── retry.py                   # Unchanged
│   ├── circuit_breaker.py         # Unchanged
│   ├── rate_limit.py              # Modified: imports from broker_vocab
│   ├── ws_reconnect.py            # Unchanged
│   ├── http_client.py             # Unchanged
│   ├── jwt_expiry.py              # Unchanged
│   ├── totp_cooldown.py           # Modified: imports from paths
│   ├── capabilities.py            # Unchanged
│   ├── quote_normalize.py         # Unchanged
│   ├── symbol_resolver.py         # DELETED
│   └── wire_mapper.py             # DELETED
├── dhan/
│   ├── __init__.py                # Unchanged
│   ├── gateway.py                 # Modified: extends BaseBrokerGateway
│   ├── connection.py              # Modified: extends BaseBrokerConnection
│   ├── wire.py                    # Modified: extends BaseBrokerWire
│   ├── config.py                  # Modified: imports from paths
│   ├── auth.py                    # Unchanged
│   └── adapters/
│       ├── __init__.py
│       ├── orders.py              # Modified: extends BaseOrdersAdapter
│       ├── market_data.py         # Modified: extends BaseMarketDataAdapter
│       ├── portfolio.py           # Modified: extends BasePortfolioAdapter
│       ├── instruments.py         # Modified: extends BaseInstrumentAdapter
│       └── streaming.py           # Modified: extends BaseStreamingAdapter
├── upstox/
│   └── (same structure as dhan/)
└── paper/
    └── (same structure, extends base classes)
```

### 5.2 Boundary Rules

1. **`domain/` must never import from `plugins/`** — domain defines interfaces; plugins implement them.
2. **`plugins/brokers/common/` must never import from `plugins/brokers/dhan/` or `upstox/`** — common is the foundation; brokers depend on it.
3. **`plugins/brokers/{dhan,upstox,paper}/` may only import from `plugins/brokers/common/` and `domain/`** — no cross-broker imports.
4. **`plugins/brokers/{dhan,upstox}/adapters/` may only import from their parent broker package and `common/`** — no sibling broker adapter imports.
5. **All transport access must go through `BaseTransport`** — no direct `urllib.request` usage in adapters.
6. **All wire conversion must go through `BaseBrokerWire`** — no module-level mutable dicts.
7. **`common/broker_vocab.py` is the single source of truth for all broker constants** — no duplicate constants in broker-specific files.

### 5.3 Coding Standards to Enforce

1. **All price values must use `Decimal`** — never `float` for monetary values. Use `Price(value=Decimal(str(raw)))`.
2. **`transition_to()` return value MUST be captured** — `order = order.transition_to(OrderStatus.SUBMITTED)`, never `order.transition_to(...)` without assignment.
3. **All gateway methods must use `get_` prefix** — `get_quote`, `get_ltp`, `get_depth`, `get_history`, `get_positions`, `get_holdings`, `get_funds`.
4. **`mass_status()` must return `BrokerSnapshot`** — not `dict[str, Any]`.
5. **All instrument adapters must use `load_instruments()` and `resolve() -> Instrument | None`** — consistent naming and error handling.
6. **All streaming adapters must use `feed_raw(payload: dict[str, Any])`** — consistent interface.
7. **No inline imports** — all imports at module level.
8. **No `parents[N]` path calculations** — use `repo_root()` from `common/paths.py`.

### 5.4 Guardrails to Prevent Recurrence

1. **Import linter rule**: `plugins/brokers/common/` must not import from `plugins/brokers/{dhan,upstox,paper}/`.
2. **Pre-commit hook**: Run `grep -r "transition_to.*[^=]$" v2/src/plugins/brokers/` to catch discarded return values.
3. **`__all__` declarations**: Every module must declare `__all__` to prevent accidental re-exports.
4. **ADR template**: New broker features require an ADR documenting the abstraction layer used.
5. **File size limit**: No file > 400 lines (soft) / 650 lines (hard) — enforced by `tests/architecture/test_god_class_size.py`.
6. **Test isolation**: `clear_plugins()` called in test teardown to prevent module-level dict leakage.
7. **Protocol enforcement**: `BaseBrokerGateway` is an ABC; all gateway methods are abstract — prevents missing methods.

---

## Summary

**Total findings**: 60 (SMELL-1 through SMELL-60)
- HIGH impact: 4 (SMELL-1, SMELL-2, SMELL-3, SMELL-4, SMELL-5, SMELL-11, SMELL-22) — actually 7
- MEDIUM impact: 12
- LOW impact: 41

**Root causes**:
1. Missing shared vocabulary layer (most constants still scattered)
2. Missing service/use-case layer (gateway/connection classes mix concerns)
3. Missing domain model (raw dicts instead of typed entities)
4. Boundary violations (transport bypass, inline imports, fragile paths)
5. Premature file splitting (dead code: WireMapper, SymbolResolver)
6. Absent coding standards (inconsistent naming, return types, error handling)
7. Frozen dataclass invariant violation (systemic mutation bug)

**Refactoring plan**: 16 sequenced tasks (REF-1 through REF-16)
- Phase 1: REF-1 (shared vocabulary), REF-15 (paths), REF-13 (dead code) — foundational
- Phase 2: REF-2 (mutation fix), REF-9 (base wire), REF-10 (mutable dicts)
- Phase 3: REF-3 (base connection), REF-4 (base gateway), REF-5 (base streaming), REF-6 (base orders), REF-7 (base market data), REF-8 (base portfolio)
- Phase 4: REF-11 (standardize gateway), REF-12 (standardize streaming), REF-16 (standardize instruments), REF-14 (fix bypass)
