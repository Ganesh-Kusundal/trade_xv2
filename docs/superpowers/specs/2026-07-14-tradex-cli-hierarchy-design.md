# TradeX CLI Hierarchy Design — v2 (corrected)

**Date:** 2026-07-14 (revised)
**Status:** SUPERSEDED by the analytics-first pivot (2026-07-14, later same day).
Product direction changed: the CLI drops `order`/`position`/`portfolio` as
top-level groups entirely (not merely routes them through the composition
root as this v2 specified) and becomes an analytics/research console
(`scanner`/`pattern`/`support`/`volume`/`market`/`indicator`/`strategy`/
`backtest`/`report`, broker reduced to market-data + lifecycle). The
composition-root findings below (§0 code-facts, `CommandDispatcher`,
`present()`, `PreferencesStore` reuse) remain accurate and reusable for the
surviving (non-execution) commands. See `context/project-overview.md` §1/§2/§6
for the current product scope and
`context/progress-tracker.md`'s "Analytics-first CLI pivot" entry for the
decision record. Kept below for historical reference only — do not implement
the `order`/`position`/`portfolio` groups in §4.

---

**Original status (pre-pivot, kept for history):** REVISED — supersedes the
"Approved for implementation" v1. v1 was authored against a fabricated model
of the codebase (claimed 3 surfaces / 44 commands / clean slate) that does
not match the actual code. This version is grounded in a graphify + code read
of the real tree.

---

## 0. What actually exists today (verified)

| Fact | Reality (code-confirmed) | v1 claim |
|---|---|---|
| CLI surfaces | 2: `tradex.cli:tradex` facade (`broker`, `ui`, `config`, `version`) and `interface.ui.main:main` (~70-command dispatcher, `COMMAND_HANDLERS` + explicit branches). `tradex ui X` re-invokes `main()` with stripped argv. | "3 overlapping surfaces: `tradex broker` (35), `tradex ui` (44+), legacy `broker`" |
| `src/cli/` | **Does not exist** (0 files). | "Approach A — new `src/cli/` clean slate" |
| Composition root | `runtime/commands/CommandDispatcher` + `OrderCommandHandler`/`SubscribeCommandHandler`/`HistoryCommandHandler` (import-linter-guarded, no `brokers.*`). `cli.py → open_session() → CommandDispatcher`. | Not mentioned |
| Trade spine routing | `main.py:_bootstrap_trade_runtime` → `build_runtime` (runtime root). Risk gate + idempotency live here. | "CLI → application.oms directly" |
| Rendering | `brokers.cli._render.present()` already does quiet>json>yaml>human, piped→JSON, domain-type dispatch. | Re-spec'd as new `cli/rendering/` |
| Services | `brokers.services.*` (place_order, get_quote, get_positions, get_holds, …) + `brokers.services.operations` (run_doctor, run_health, run_certify, run_verify, run_mapping, run_diagnose, status_from_session). | Re-spec'd as 5 new `brokers/services/*_service.py` |
| Default broker auth | Dhan = `dhanhq` + `pyotp` → **client_id + client_secret + TOTP + PIN**. Upstox = OAuth. | "OAuth token/refresh only" |
| Real-money guard | `--risk-fail-open` explicit-consent flag in `main.py`; `BrokerService` refuses `RISK_FAIL_OPEN=1` env without the flag. | Dropped |
| Textual | **Optional** dep (`[project.optional-dependencies] tui`); only `dashboard.py` (a Rich validation table, not Textual) exists. | "Build TUI with Textual" as headline |

**Consequence:** v1's "delete `interface/ui/main.py`" + "clean-slate `src/cli/`" would
(1) orphan ~55 of ~70 existing commands, (2) bypass the sanctioned composition
root, and (3) duplicate three working modules. This revision fixes all three.

---

## 1. Problem (restated, accurate)

The CLI has **two real issues**, not a structural collapse:

1. **Two entry points, one facade.** `tradex broker` (Click, `brokers/cli/broker.py`)
   and `tradex ui`/`interface.ui.main` (argparse-style, `main.py`) are parallel
   command trees with overlapping commands (`quote`, `order`, `positions`,
   `holdings`, `funds`, `depth`, `option-chain`, `instrument`, `auth`, `doctor`,
   `health`…) and **different output/dispatch conventions**. That is the genuine
   duplication worth resolving.
2. **No flat, broker-agnostic top-level groups** (`tradex quote`, `tradex order`
   as peers of `tradex broker`), and **broker lifecycle commands**
   (`add`/`remove`/`login`/`logout`/`token`/`instruments sync`) are missing.

Everything else v1 listed (TUI, wizards, JSON envelope) is either already
partially present or a nice-to-have — not a reason to rebuild the tree.

---

## 2. Decisions (revised)

| Decision | Choice | Why |
|---|---|---|
| Scope | **Restructure the top-level hierarchy only**; reuse existing internals | ponytail: shortest diff; don't rebuild working modules |
| CLI consolidation | Merge into ONE Click surface rooted at `tradex.cli`. `interface.ui.main` becomes an internal dispatch backend, not a user-facing entry | Removes duplication #1 cleanly |
| Composition root | ALL commands route through `runtime/commands/CommandDispatcher` (existing) | Enforces architecture invariants #2/#3 — single root, broker selected once |
| Reuse, not copy | Import `brokers.cli._render.present`, `brokers.cli._preferences.PreferencesStore`, and wrap `brokers.services.*` | v1's "copy into `cli/`" violates DRY + the stated "clean slate" |
| New modules | **Only** what doesn't exist: `BrokerConfigStore`, `AuthService` (per-broker), `InstrumentService`, `HealthService`, `RateLimitService` — added to `brokers/services/` (NOT a new package) | Keeps one service layer, not two |
| TUI dashboard | Opt-in (`tradex broker --dashboard` or `tradex tui`); **not** default for no-arg `tradex broker` | No-arg `tradex broker` today prints help — changing it breaks scripts |
| Textual | Make `textual` a **required** dep, OR keep dashboard opt-in and clearly marked | A headline feature must be runnable on a default install |
| Auth model | Per-broker capability: Dhan = TOTP+token; Upstox = OAuth. `AuthService` branches on `BrokerId` capability | v1's OAuth-only silently breaks the default (Dhan) broker |
| Credentials | Encrypt with **passphrase-derived** key (PBKDF2/Argon2) or OS keychain — NOT a machine-specific seed | Machine-seed Fernet = recoverable live creds = real-money unsafe |
| Risk gate | Live orders **must** pass the production gate; `--risk-fail-open` explicit consent carried forward from `main.py` | v1 dropped the guard |
| JSON output | **Keep** the existing `present()` shape (raw `safe_serialize(data)`); do NOT introduce the new `{status,data,meta}` envelope silently | Envelope change breaks all CI/agent/MCP consumers |

---

## 3. Package Structure (revised)

No new top-level package. Reorganize under the existing `tradex.cli` + `interface.ui.commands`.

```
src/tradex/cli.py            # single Click facade — registers all groups (was: broker/ui/config/version)
  +-- app.py                 # root group, global options (--broker --json --yaml --quiet)  [NEW, small]
  +-- errors.py              # reuse brokers/cli/_errors.handle_cli_errors
  +-- rendering/             # REUSE brokers/cli/_render.py as src/tradex/cli/rendering.py (move, not copy)
  +-- commands/             # [NEW] thin Click wrappers, one module per group
        broker.py            # lifecycle: list/add/remove/connect/disconnect/login/logout/
                             #   switch/current/status/health/capabilities/token/instruments/rate-limit
        quote.py  order.py  position.py  portfolio.py  instrument.py
        account.py market.py auth.py cache.py doctor.py logs.py version.py
src/brokers/services/        # EXTEND (not duplicated)
  +-- broker_config.py       # BrokerConfigStore          [NEW]
  +-- auth_service.py        # AuthService (per-broker)   [NEW]
  +-- instrument_service.py   # InstrumentService          [NEW]
  +-- health_service.py       # HealthService              [NEW]
  +-- rate_limit_service.py   # RateLimitService           [NEW]
src/interface/ui/commands/   # STAYS — already has the real implementations
  +-- dashboard.py            # becomes Textual TUI (opt-in)
  +-- (analytics, validate, certify, risk, oms, journal,
       load_test, news, websocket, events, views, asset,
       feed, options_sync, …)  # ~55 commands — RE-HOMED, not deleted
src/runtime/commands/        # STAYS — the sanctioned composition root all commands route through
```

### Dependency direction (unchanged contract)

```
src/tradex/cli/commands/*  -->  runtime/commands.CommandDispatcher   (composition root)
                          -->  brokers/services/*                    (broker ops)
                          -->  interface/ui/commands/*               (existing impls)
                          -->  tradex/cli/rendering.present          (output)
CLI NEVER imports concrete brokers (brokers.dhan/upstox/paper).
Routing through runtime/commands keeps the import-linter "CLI broker-implementation
isolation" contract satisfied (the existing runtime/commands handlers are already clean).
```

### What gets removed

- The **duplicate** command definitions: whichever of `brokers/cli/broker.py` or
  `interface/ui/main.py` is the lesser superseded surface. Recommendation:
  `brokers/cli/broker.py` is folded into `tradex/cli/commands/*`; `interface/ui/main.py`
  remains the internal dispatch backend (its `COMMAND_HANDLERS` becomes the canonical
  registry the Click groups call).
- The deprecated `broker` entry point in `pyproject.toml` (already marked deprecated).
- The `tradex ui` pass-through command once the flat groups cover everything.

### What stays untouched

- `runtime/commands/*` — composition root (extended with any missing handlers).
- `brokers/services/*` — service layer (extended with the 5 new modules).
- `brokers/cli/_render.py`, `_preferences.py`, `_errors.py` — moved into `tradex/cli/`, not rewritten.
- `interface/ui/commands/*` — the ~55 real implementations.

---

## 4. Command Hierarchy (revised)

### Top-level `tradex` group (single Click surface)

```
tradex [--json] [--yaml] [--quiet] [--broker ID]
  +-- broker        # Broker lifecycle & identity
  +-- quote         # Market quotes
  +-- order         # Order management (via runtime/commands → OMS + RiskGate)
  +-- position      # Position tracking
  +-- portfolio     # Holdings, funds, summary
  +-- instrument    # Instrument lookup & sync
  +-- account       # Account info
  +-- market        # Market status & hours
  +-- config        # CLI preferences (reuse existing)
  +-- auth          # Read-only auth status
  +-- cache         # Instrument cache mgmt
  +-- doctor        # Environment pre-flight (wrap run_doctor)
  +-- logs          # Log inspection
  +-- version       # Version info
  # Plus: analytics, validate, certify, risk, oms, journal, load-test,
  #       news, websocket, events, views, asset, feed, options-sync, dashboard —
  #       re-homed from interface/ui/main.py, each as its own group.
```

**No-arg `tradex broker` keeps printing help/list** (today's behavior). The TUI
dashboard is opt-in via `tradex broker --dashboard` or `tradex tui`.

### `tradex order` — through the composition root (NOT directly to OMS)

```
tradex order place  SYMBOL --side BUY --qty N --type MARKET [--price P]
tradex order cancel ORDER_ID
tradex order modify ORDER_ID [--qty N] [--price P]
tradex order list   [open|all]
```

Routing:
`order place` → `runtime.commands.PlaceOrderCommand` → `CommandDispatcher`
→ `OrderCommandHandler` → `OrderManager.place_order` (sync risk check + idempotency
already there). **Paper and live share this path**; live additionally requires the
production RiskGate. `--risk-fail-open` is forwarded and explicitly required for
the placeholder-capital path (mirrors `main.py`).

---

## 5. New Broker-Lifecycle Services (added to `brokers/services/`)

### `broker_config.py` — `BrokerConfigStore`

Persistent registry. **Reuse `brokers.cli._preferences.PreferencesStore` as the
storage primitive**; extend with broker registry fields. Single source of truth for
`broker.default` (already how `switch`/current work) — do NOT invent a second
`~/.tradex/brokers.json` registry that diverges from `PreferencesStore`.

```python
class BrokerConfigStore:
    def list_brokers() -> list[BrokerConfig]
    def add_broker(broker_id, nickname, credentials) -> BrokerConfig
    def remove_broker(broker_id, *, delete_credentials: bool) -> None
    def get_default() -> str
    def set_default(broker_id) -> None
    def get(broker_id) -> BrokerConfig | None
```

### `auth_service.py` — `AuthService` (per-broker capability)

```python
class AuthService:
    def login(self, broker_id, *, method: AuthMethod, **creds) -> AuthResult
    def logout(broker_id) -> None
    def refresh_token(broker_id) -> AuthResult
    def revoke_token(broker_id) -> None
    def get_token_status(broker_id) -> TokenStatus
```

- **Dhan**: `method=TOTP` → client_id + client_secret + TOTP(pin) → token. No
  browser OAuth. `login_browser` is invalid for Dhan and must not be offered.
- **Upstox**: `method=OAUTH` → browser redirect → token + refresh.
- The method set is derived from `BrokerId` capability, not a hardcoded assumption.

### `instrument_service.py` — `InstrumentService`

Exchange + symbol combo (not fuzzy). **Wrap existing `brokers/services/instrument_lookup`**
rather than re-implementing search/verify/sync.

```python
class InstrumentService:
    def search(exchange, symbol, *, segment=None) -> list[InstrumentMatch]
    def verify(broker_id) -> VerificationReport
    def sync(broker_id, *, progress_callback) -> SyncResult
    def stats(broker_id) -> InstrumentStats
    def clear_cache(broker_id) -> None
```

### `health_service.py` — `HealthService`

**Wrap `brokers/services/operations`** (`run_doctor`, `run_health`, `run_certify`,
`status_from_session`) — these already do DNS→auth→REST→WS→order API checks. Do not
rebuild the checks.

```python
class HealthService:
    def check_health(broker_id) -> HealthReport
    def run_doctor() -> DoctorReport
    def check_connectivity(broker_id) -> ConnectivityReport
```

### `rate_limit_service.py` — `RateLimitService`

```python
class RateLimitService:
    def get_status(broker_id) -> RateLimitStatus
```

**Wire this into the TUI dashboard refresh loop** (v1 defined it but never used it).

### Credential storage (security-corrected)

- Encrypt at rest with a **passphrase-derived** key (PBKDF2-HMAC-SHA256 or
  Argon2id, salt stored alongside). On first use, prompt for a passphrase; cache
  the unlocked key in the process only (never on disk).
- If OS keychain is available (macOS Keychain / libsecret), prefer it.
- **Do NOT** derive the key from a machine-specific seed — that is recoverable by
  anyone with file + machine access and is unacceptable for live broker creds.
- Keep credentials separate from `.env.*` (dev API keys), as v1 correctly noted.

---

## 6. Interactive Wizards & TUI Dashboard (revised)

### Wizards — `src/tradex/cli/wizards/` (only if flags alone are insufficient)

Every trading command works two ways: flags for CI, interactive wizard by default.
Reuse `prompt_toolkit` only where arrow-selection genuinely helps; plain
`click.prompt` suffices for most inputs (ponytail: don't pull a framework for
text input).

```python
# order_wizard.py
def run_order_wizard(session) -> OrderRequest
  # symbol -> exchange auto-resolved via InstrumentService.search
  # side / type / qty / price -> validated inputs
  # confirm panel -> Y/n

# login_wizard.py
def run_login_wizard(broker_id, auth_service) -> AuthResult
  # method picker constrained by broker capability (Dhan=TOTP, Upstox=OAuth)

# broker_add_wizard.py
def run_broker_add_wizard(store) -> BrokerConfig
```

### TUI Dashboard — opt-in, real-time-safe

- Launched via `tradex broker --dashboard` / `tradex tui`. No-arg `tradex broker`
  stays help/list.
- If Textual remains optional, gate the command: `tradex tui` prints
  "install `tradexv2[tui]`" if unavailable. If dashboard is a headline feature,
  promote `textual` to a required dependency.
- **Panel refresh must handle failure** (v1 omitted this):
  - Reuse a single shared gateway/session (don't open one per panel).
  - On WS drop: exponential backoff reconnect (use existing `infrastructure/resilience/backoff.py`).
  - On `RateLimitStatus` near window: throttle refreshes via `RateLimitService`.
  - On error: show a red error state in the panel, never crash the app silently.
- Data sources reuse `portfolio.get_positions/get_orders/get_funds` (existing).

---

## 7. Output Rendering (reuse, don't re-spec)

**Keep `brokers/cli/_render.present()` as the single renderer.** Move it to
`tradex/cli/rendering.py`. It already implements:

- Mode priority: `--quiet` > `--json`/`--yaml` > human.
- Piped → JSON automatically (`not sys.stdout.isatty()`).
- Domain-type dispatch for `QuoteSnapshot`, `MarketDepth`, `HistoricalSeries`,
  `OptionChain`, capabilities, records, KV.

**Do NOT introduce the new `{status,data,meta}` / `{status,error}` envelope.**
Downstream consumers (CI, agents, MCP server `datalake-mcp`, `cli_endpoint`
pytest markers) parse the current `safe_serialize(data)` shape. A silent envelope
swap is a production-breaking change; if an envelope is wanted it needs a versioned
contract + migration + a deprecation window — out of scope for this restructure.

Commands return structured data; `present()` formats. Commands never print directly
(already the convention in `brokers/cli/broker.py`).

---

## 8. Migration Plan (revised — parity-gated, no big-bang delete)

### Phase 0: Pre-flight (blocking)
1. Enumerate **all ~70** existing `interface/ui/main.py` commands; assign each a
   destination group in this spec. No command is deleted until it has a home.
2. Add `src/tradex/cli/rendering.py` = moved `brokers/cli/_render.py` (no behavior change).
3. Confirm `runtime/commands` covers order/subscribe/history; add handlers for any
   missing command type (e.g. positions, portfolio) before wiring CLI to them.

### Phase 1: Single Click surface (no deletion)
1. `tradex/cli/app.py` — root group + global options.
2. `tradex/cli/commands/version.py`, `config.py`, `doctor.py` (wrap `run_doctor`),
   `quote.py`, `instrument.py`, `position.py`, `portfolio.py` — thin wrappers over
   `brokers/services/*` → `runtime/commands` (read-only first).
3. `tradex/cli/commands/order.py` — through `CommandDispatcher` (live RiskGate +
   `--risk-fail-open` forward).
4. Both `tradex broker` (old) and `tradex <group>` (new) work simultaneously.

### Phase 2: New services (extend `brokers/services/`)
1. `broker_config.py` (on top of `PreferencesStore`).
2. `auth_service.py` (per-broker: Dhan TOTP / Upstox OAuth).
3. `instrument_service.py` (wrap `instrument_lookup`).
4. `health_service.py` (wrap `operations`).
5. `rate_limit_service.py`.

### Phase 3: Broker lifecycle + re-home remaining commands
1. `tradex/cli/commands/broker.py` — add/remove/connect/… (uses the new services).
2. Re-home the ~55 `interface/ui/main.py` commands as their own Click groups,
   one per existing `interface/ui/commands/*.py` implementation. Each re-home:
   write module → write/keep tests → verify old+new both work → next.

### Phase 4: Interactive + TUI (opt-in)
1. `wizards/prompts.py`, `order_wizard.py`, `login_wizard.py`, `broker_add_wizard.py`.
2. `dashboard` as Textual TUI, launched opt-in, with backoff/rate-limit/error states.

### Phase 5: Cleanup (only after 100% command parity)
1. Fold `brokers/cli/broker.py` into `tradex/cli/commands/*`.
2. `interface/ui/main.py` becomes internal backend (or deleted if every command is
   re-homed and tests pass).
3. Remove deprecated `broker` entry point from `pyproject.toml`.
4. Update import-linter contracts (keep `tradex` + `interface` + `runtime` roots;
   no new top-level package was added, so contracts are unchanged in scope).
5. Move CLI tests to `tests/unit/tradex/cli/`.

### Test strategy
- Old tests for `brokers/cli/` and `interface/ui/main.py` stay green until Phase 5.
- Every new command has an offline `cli_endpoint` smoke test (existing marker).
- Live-readonly / sandbox tests gated by the existing markers (never default run).
- No coverage drop at any phase boundary.

---

## 9. Invariant / safety checklist (must hold)

- [ ] All commands route through `runtime/commands` composition root (no direct
      `application`/`brokers.*` calls from CLI).
- [ ] Live orders pass the production RiskGate; `--risk-fail-open` is explicit
      and forwarded; placeholder-capital path refuses without it.
- [ ] Auth model covers Dhan (TOTP) and Upstox (OAuth) via capability, not assumption.
- [ ] Credentials encrypted with passphrase/keychain key, not machine seed.
- [ ] `present()` shape unchanged; no silent envelope swap.
- [ ] No-arg `tradex broker` unchanged (help/list); TUI is opt-in.
- [ ] Textual either required or dashboard command self-documents the install.
- [ ] Zero-parity: paper and live share the same order path.
- [ ] Every one of the ~70 existing commands is re-homed before any deletion.
