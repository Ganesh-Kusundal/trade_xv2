# TradeX CLI Hierarchy Design

**Date:** 2026-07-14
**Status:** Approved for implementation
**Approach:** A — New `src/cli/` package (clean slate)

---

## 1. Problem

The current CLI has three overlapping surfaces:

- `tradex broker` — 35 subcommands flattened under one group
- `tradex ui` — 44+ commands in `interface/ui/main.py`
- `broker` — legacy entry point

The spec calls for a flat top-level hierarchy (`tradex quote`, `tradex order`, `tradex position` as peers of `tradex broker`), one executable, interactive by default, broker-agnostic, with rich terminal output. Today everything is nested under `tradex broker`, broker lifecycle commands (`add`, `remove`, `login`, `logout`, `token`, `instruments sync`) are missing, and there is no TUI dashboard.

---

## 2. Decisions

| Decision | Choice |
|---|---|
| Scope | Full hierarchy restructure — flat top-level groups |
| CLI consolidation | Merge `tradex ui` into `tradex` — one surface |
| Broker lifecycle depth | Full implementation (services + CLI) |
| TUI dashboard | Build with Textual |
| Interactivity | Interactive by default, flags for CI |
| Instrument search | Exchange + symbol combo, not fuzzy |

---

## 3. Package Structure

```
src/cli/
  __init__.py           # tradex Click group, registers all subcommands
  app.py                # root group definition, global options
  preferences.py        # PreferencesStore (extended from brokers/cli/_preferences.py)
  errors.py             # handle_cli_errors decorator
  rendering/
    __init__.py         # present() dispatcher
    tables.py           # Rich table rendering
    json_yaml.py        # JSON/YAML serialization
    quiet.py            # quiet mode suppression
    domain_types.py     # QuoteSnapshot, MarketDepth, etc. renderers
  wizards/
    __init__.py
    prompts.py          # shared Prompt Toolkit helpers
    order_wizard.py     # interactive order placement
    login_wizard.py     # browser/token login flow
    broker_add_wizard.py
  dashboard/
    __init__.py
    app.py              # Textual TUI application
    panels/             # status, actions, positions, orders panels
  commands/
    broker.py           # lifecycle: add/remove/connect/disconnect/login/logout/switch/current/status/health/capabilities/token/instruments/rate-limit
    quote.py            # tradex quote SYMBOL
    order.py            # tradex order place/cancel/modify/list
    position.py         # tradex position list
    portfolio.py        # tradex portfolio holdings/funds/summary
    instrument.py       # tradex instrument search/verify/sync/stats (top-level; broker-specific ops under `tradex broker instruments`)
    account.py          # tradex account info
    market.py           # tradex market hours/status
    config.py           # tradex config list/get/set/edit/reset
    auth.py             # tradex auth status (read-only; login/logout under `tradex broker`)
    cache.py            # tradex cache status/stats/clear/refresh (instrument cache)
    doctor.py           # tradex doctor
    logs.py             # tradex logs tail/show/clear
    version.py          # tradex version
```

### Dependency Direction

```
src/cli/commands/*  -->  src/brokers/services/*    (broker ops)
                    -->  src/application/*         (OMS, portfolio)
                    -->  src/runtime/*             (composition root)
                    -->  src/cli/rendering/         (output)
                    -->  src/cli/wizards/           (interactive)
```

CLI never imports concrete brokers (`brokers.dhan/upstox/paper`). All routing goes through `brokers/services/` or `runtime/`.

### What Gets Removed

- `src/brokers/cli/` — fully replaced by `src/cli/`
- `src/interface/ui/main.py` — commands distributed to `src/cli/commands/`
- `src/tradex/cli.py` — replaced by `src/cli/__init__.py`
- Old `broker` entry point from `pyproject.toml`

### What Stays Untouched

- `src/brokers/services/` — the service layer the CLI calls (extended with new modules)
- `src/interface/ui/services/` — BrokerService, compose.py (CLI imports from here)
- `src/application/`, `src/runtime/` — no changes

---

## 4. Command Hierarchy

### Top-level `tradex` group

```
tradex [--json] [--yaml] [--quiet] [--broker ID]
  +-- broker        # Broker lifecycle & identity
  +-- quote         # Market quotes
  +-- order         # Order management
  +-- position      # Position tracking
  +-- portfolio     # Holdings, funds, summary
  +-- instrument    # Instrument lookup & sync
  +-- account       # Account info
  +-- market        # Market status & hours
  +-- config        # CLI preferences
  +-- auth          # Read-only auth status (login/logout are under `tradex broker`)
  +-- cache         # Instrument cache management (status/stats/clear/refresh)
  +-- doctor        # Environment pre-flight
  +-- logs          # Log inspection
  +-- version       # Version info
```

### `tradex broker` — lifecycle only (15 subcommands)

```
tradex broker
  +-- list            # Show all brokers with connected/active/account status
  +-- add             # Interactive: pick broker -> nickname -> credentials
  +-- remove          # Remove broker config (with cascade confirm)
  +-- connect         # Connect + verify (token, API, instruments, WS)
  +-- disconnect      # Disconnect session
  +-- login           # Interactive: browser or token auth
  +-- logout          # Clear session credentials
  +-- switch          # Set default broker (interactive picker or arg)
  +-- current         # Show active broker
  +-- status          # Auth/REST/WS/orders/rate-limit status
  +-- health          # DNS -> auth -> REST -> WS -> order API checks
  +-- capabilities    # Show capability matrix
  +-- token           # Token show/refresh/revoke
  +-- instruments     # sync/verify/stats/clear-cache (broker-specific ops; search is top-level `tradex instrument search`)
  +-- rate-limit      # Show current rate-limit state
```

Without arguments: launches the TUI dashboard.

### `tradex order` — full OMS routing

```
tradex order
  +-- place           # Interactive wizard OR flags (--symbol --side --qty --type)
  +-- cancel          # tradex order cancel ORDER_ID
  +-- modify          # Interactive OR flags
  +-- list            # List open/all orders
```

Live broker orders route through `BrokerService.place_order()` -> OMS (RiskGate + idempotency + reconciliation). Paper orders go through the same path but skip the production-readiness gate.

### Flat commands

```
tradex quote RELIANCE [--json]
tradex position list [--json]
tradex portfolio holdings [--json]
tradex portfolio funds [--json]
tradex portfolio summary [--json]
```

### Group option propagation

`--broker`, `--json`, `--yaml`, `--quiet` are defined once on the root `tradex` group and propagated via Click context. Individual commands read them from `ctx.obj`.

---

## 5. Broker Lifecycle Services

New application services in `src/brokers/services/`:

### `broker_config.py` — BrokerConfigStore

Persistent broker registry at `~/.tradex/brokers.json`:

```json
{
  "brokers": {
    "dhan": {
      "nickname": "Primary Account",
      "credentials_path": "~/.tradex/credentials/dhan.enc",
      "connected": false,
      "added_at": "2026-07-14T10:00:00Z"
    }
  },
  "default": "dhan"
}
```

```python
class BrokerConfigStore:
    def list_brokers() -> list[BrokerConfig]
    def add_broker(broker_id, nickname, credentials) -> BrokerConfig
    def remove_broker(broker_id, *, delete_credentials: bool) -> None
    def get_default() -> str
    def set_default(broker_id) -> None
    def get(broker_id) -> BrokerConfig | None
```

### `auth_service.py` — AuthService

Authentication flows:

```python
class AuthService:
    def login_browser(broker_id) -> AuthResult
    def login_token(broker_id, token) -> AuthResult
    def logout(broker_id) -> None
    def refresh_token(broker_id) -> AuthResult
    def revoke_token(broker_id) -> None
    def get_token_status(broker_id) -> TokenStatus
```

Browser login: starts local HTTP server on random port, opens broker OAuth URL with `redirect=localhost:{port}`, receives access token via callback, encrypts and stores via `BrokerConfigStore`.

### `instrument_service.py` — InstrumentService

Exchange + symbol combo lookup (not fuzzy):

```python
class InstrumentService:
    def search(exchange: str, symbol: str, *, segment: str | None = None) -> list[InstrumentMatch]
    def verify(broker_id) -> VerificationReport
    def sync(broker_id, *, progress_callback) -> SyncResult
    def stats(broker_id) -> InstrumentStats
    def clear_cache(broker_id) -> None
```

CLI usage:

```
tradex instrument search NSE RELIANCE
tradex instrument search NFO "NIFTY 29000 CE"
tradex instrument search NSE RELIANCE --segment Option
```

Output:

```
Exchange  Segment  Symbol              Instrument ID  Expiry
NSE       Equity   RELIANCE            2885           --
NFO       Future   RELIANCE 25 JUL     142885         2026-07-31
NFO       Option   RELIANCE 2900 CE    242885         2026-07-31
NFO       Option   RELIANCE 2900 PE    342885         2026-07-31
```

### `health_service.py` — HealthService

```python
class HealthService:
    def check_health(broker_id) -> HealthReport
    def run_doctor() -> DoctorReport
    def check_connectivity(broker_id) -> ConnectivityReport
```

### `rate_limit_service.py` — RateLimitService

```python
class RateLimitService:
    def get_status(broker_id) -> RateLimitStatus
```

### Credential storage

Credentials encrypted at rest using `cryptography.fernet` with a key derived from a machine-specific seed. Encrypted file at `~/.tradex/credentials/{broker_id}.enc`. Separate from `.env.*` files (which hold API keys for development).

---

## 6. Interactive Wizards & TUI Dashboard

### Wizards — `src/cli/wizards/`

Every trading command works two ways: flags for CI, interactive wizard by default.

```python
# prompts.py — shared building blocks
def select_broker(brokers: list[str]) -> str
def confirm_action(prompt: str, *, default: bool = True) -> bool
def progress_bar(label: str, total: int) -> ContextManager

# order_wizard.py
def run_order_wizard(session: BrokerSession) -> OrderRequest
  # 1. Symbol input (text, validated against instrument index)
  # 2. Exchange auto-resolved from symbol + instrument index
  # 3. Side — BUY / SELL (arrow select)
  # 4. Quantity (number input, validated > 0)
  # 5. Order type — MARKET / LIMIT / STOP (arrow select)
  # 6. If LIMIT/STOP -> price input
  # 7. Confirm panel showing full order, Y/n

# login_wizard.py
def run_login_wizard(broker_id: str, auth_service: AuthService) -> AuthResult
  # 1. Auth method — Browser / Token (arrow select)
  # 2a. If Browser -> "Opening browser..." + waiting spinner + callback
  # 2b. If Token -> token input (hidden)
  # 3. Show account name + client ID
  # 4. "Save credentials?" Y/n

# broker_add_wizard.py
def run_broker_add_wizard(store: BrokerConfigStore) -> BrokerConfig
  # 1. Select broker from registered plugins
  # 2. Nickname input
  # 3. Delegate to login_wizard for auth
  # 4. Run connect check
  # 5. Summary panel
```

### TUI Dashboard — `src/cli/dashboard/`

Launched when `tradex broker` runs without subcommand. Built with Textual.

```
+-------------------------------------------------+
|  TradeXV2 -- Dhan (Primary)          Market: OPEN |
+------------------+------------------------------|
|  Account         |  Positions (3)               |
|  Ganesh Trading  |  RELIANCE  +500  Rs1,24,500  |
|  Client: xxxx123 |  TCS       -200  -Rs48,200   |
|                  |  NIFTY CE   10   Rs12,800    |
|  Funds           |                              |
|  Available: Rs2.54L|  Orders (1 open)           |
|  Margin:   Rs1.80L|  #DH1234 BUY RELIANCE 500   |
|                  |  Status: OPEN  P&L: +Rs1,200 |
+------------------+------------------------------+
|  Actions: [Login] [Health] [Order] [Positions]  |
|           [Instruments] [Logs] [Settings]       |
+-------------------------------------------------+
```

Panel data sources:

| Panel | Data source | Refresh |
|---|---|---|
| Header bar | `BrokerConfigStore` + `MarketStatus` | on connect/switch |
| Account | `portfolio.get_funds()` | every 30s |
| Positions | `portfolio.get_positions()` | every 10s |
| Orders | `portfolio.get_orders()` | every 10s |
| Actions | keybound buttons | user-triggered |

Action flow: pressing `[Order]` opens the order wizard inline. `[Health]` runs `HealthService.check_health()` and shows results in a modal. `[Login]` runs `login_wizard`.

Technology: Textual for the dashboard (reactive widgets, keyboard navigation, event handling). Rich for all non-TUI output (tables, progress bars, panels in regular commands).

---

## 7. Output Rendering

### Rendering layer — `src/cli/rendering/`

One `present()` function dispatches based on domain type + output mode:

```python
def present(ctx: click.Context, data: Any, *, title: str | None = None) -> None:
    mode = resolve_mode(ctx)  # quiet > json > yaml > human
    if mode == "quiet": return
    if mode == "json":  emit_json(data); return
    if mode == "yaml":  emit_yaml(data); return
    renderer = _REGISTRY.get(type(data), render_generic)
    renderer(data, title=title)
```

### Domain type renderers

| Type | Human output |
|---|---|
| `QuoteSnapshot` | K/V panel: LTP, OHLC, bid/ask, volume, change% |
| `MarketDepth` | Side/Level/Price/Qty/Orders table, top-20 bids+asks, spread footer |
| `HistoricalSeries` | Last-10-bars table + timeframe/source footer |
| `OptionChain` | CE LTP/OI / Strike / PE LTP/OI table, ATM +/-10 window |
| `HealthReport` | Checklist with pass/fail per check, summary footer |
| `DoctorReport` | Grouped sections (Environment, Broker, Connectivity, Config) |
| `InstrumentMatch` | Exchange/Segment/Symbol/ID/Expiry table |
| `OrderRequest` / `OrderResult` | Order detail panel |
| `RateLimitStatus` | Remaining/limit/window/reset gauge |
| `dict` / `list` | Generic K/V panel / table |

### Mode resolution priority

1. `--quiet` flag -> suppress all output
2. `--json` flag OR stdout is not a TTY -> JSON (machine-readable by default when piped)
3. `--yaml` flag -> YAML
4. Otherwise -> Rich human tables

### Consistent envelope

Success:

```json
{
  "status": "ok",
  "data": { ... },
  "meta": { "broker": "dhan", "timestamp": "2026-07-14T10:30:00Z" }
}
```

Error:

```json
{
  "status": "error",
  "error": { "code": "BROKER_NOT_CONNECTED", "message": "...", "remediation": "..." }
}
```

Every command returns structured data; `present()` handles formatting. Commands never print directly.

---

## 8. Migration Plan

### Phase 1: Foundation (new package, no breakage)

1. Create `src/cli/` package with `app.py`, `preferences.py`, `errors.py`, `rendering/`
2. Copy rendering from `brokers/cli/_render.py` -> `cli/rendering/`
3. Copy preferences from `brokers/cli/_preferences.py` -> `cli/preferences.py`
4. Copy error handling from `brokers/cli/_errors.py` -> `cli/errors.py`
5. Wire `pyproject.toml` entry point: `tradex = "cli.app:tradex"` (alongside existing)
6. Both entry points work simultaneously

### Phase 2: Command migration (one group at a time)

Order: safe read-only first, trading last.

1. `cli/commands/version.py` — proves the pattern
2. `cli/commands/config.py` — no broker dependency
3. `cli/commands/doctor.py` — wraps `operations.run_doctor`
4. `cli/commands/quote.py` — wraps `market_data.get_quote`
5. `cli/commands/instrument.py` — wraps `instrument_lookup.*`
6. `cli/commands/position.py` — wraps `portfolio.get_positions`
7. `cli/commands/portfolio.py` — wraps `portfolio.get_holdings/get_funds`
8. `cli/commands/order.py` — wraps `orders.place_order/cancel/modify` + OMS routing
9. `cli/commands/account.py` — wraps `portfolio` + `account` services
10. `cli/commands/market.py` — wraps market hours/status
11. `cli/commands/auth.py` — wraps new `AuthService`
12. `cli/commands/cache.py` — wraps cache management
13. `cli/commands/logs.py` — new, reads log files
14. `cli/commands/broker.py` — last, largest

Each command: write module -> write tests -> verify old + new both work -> next.

### Phase 3: New services

1. `broker_config.py` + `BrokerConfigStore`
2. `auth_service.py` + `AuthService`
3. `instrument_service.py` + `InstrumentService`
4. `health_service.py` + `HealthService`
5. `rate_limit_service.py`

### Phase 4: Interactive layer

1. `wizards/prompts.py` — shared prompt helpers
2. `wizards/order_wizard.py`
3. `wizards/login_wizard.py`
4. `wizards/broker_add_wizard.py`

### Phase 5: TUI Dashboard

1. `dashboard/app.py` — Textual application shell
2. `dashboard/panels/` — account, positions, orders, actions panels
3. Wire `tradex broker` (no subcommand) -> dashboard launch

### Phase 6: Cleanup

1. Delete `src/brokers/cli/` entirely
2. Delete `src/interface/ui/main.py`
3. Delete `src/tradex/cli.py`
4. Remove old `broker` entry point from `pyproject.toml`
5. Update import-linter contracts
6. Move CLI tests to `tests/unit/cli/`

### Test strategy

Every phase has tests written alongside. Old tests for `brokers/cli/` are kept running until Phase 6 deletes the old package. No test coverage drops at any phase boundary.
