# TradeXV2 Architecture Review — Part 2 (Full Exhaustive Sweep)

**Status:** Read-only, second review wave. 8 parallel agents covered every package the first wave
skipped or only skimmed: `tradex/runtime` composition root, security/auth, REST API surface,
market_data/config/datalake ingestion, infrastructure/reconciliation, backtest engine math,
shared/providers/plugins/scripts/packaging/CI, and the execution-orchestration seam.

**This wave found several P0 defects the first wave MISSED** — including one that means the REST API
cannot boot at all, and a live-credential leak via a git-tracked file.

Every claim below is file:line-verified against the working tree (2026-07-09).

---

## 0. New Critical Findings (P0 — must fix before any real capital)

| # | Finding | Evidence | Why it's worse than Wave 1 knew |
|---|---------|----------|----------------------------------|
| P0-A | **REST API fails to boot.** `api/main.py:224` imports `runtime.production_config.validate_production_config`, which does not exist (grep: no definition). `create_app` raises `ImportError` on every boot. | `api/main.py:224`; `runtime/production_config.py` has no such fn | The entire API server is non-functional. |
| P0-B | **Live Dhan credentials are git-tracked.** `.env.local` (with `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN`/PIN/TOTP) is tracked by git and is *rewritten on every token refresh* (`factory.py:547,555`). | `git ls-files` lists `.env.local`; `brokers/dhan/factory.py:547` | Full account compromise on any repo access. `.env.upstox` + token-state files ARE ignored — inconsistent. |
| P0-C | **API auth is fail-open.** `api/auth.py:88` `_validate_api_key_value` returns immediately unless `AUTH_MODE == "api_key"` (any typo/"none" disables all auth). Every order/cancel/kill-switch route becomes unauthenticated. | `api/auth.py:88` | Trading control plane open to anyone if misconfigured. |
| P0-D | **Zero-parity broken by timezone.** Live/replay bars are forced **UTC** (`historical_mapper.py:14`); parquet backtests are **naive IST** (`normalize.py:100`); a 5h30m offset. `sync_options.py:76` subtracts 5h30m to compensate — proving the system knows but never unifies. | `historical_mapper.py:14`, `normalize.py:100`, `datalake/gateway.py:49` | Backtests run on a shifted clock → signals/results systematically wrong. |
| P0-E | **Backtest equity curves are arithmetically wrong (3 ways, all wrong).** Replay = no mark-to-market (frozen at cost); Fast = double-counts notional (+1 notional); Paper = undercounts (−1 notional). | `analytics/backtest/models.py:284`, `fast_backtest.py:197`, `paper/models.py:246` | Every Sharpe/drawdown/return number invalid AND the 3 engines disagree on the same trades. |
| P0-F | **Default fill = look-ahead.** `run_backtest.py` never sets `fill_model`, so signals fill at the same bar's close they were computed from. | `models.py:161`, `engine.py:391` | Structural upward PnL bias live can never reproduce. |
| P0-G | **`ExecutionComposer` bypasses OMS entirely** (no idempotency, no risk, no audit; kill-switch is a no-op when `risk_manager` is None). CLI `place-orders`/`cancel`/`modify` use it; the CLI never injects `risk_manager` (`composer_helpers.py:103`), so the operator's kill-switch cannot stop those orders. | `application/composer/execution.py:106,118,55`; `cli/composer_helpers.py:103` | A live money hole: manual/CLI orders skip all safety. |
| P0-H | **Reconciliation never heals + dedup ledger evicts after 24h.** `auto_repair=False` hardcoded at every wiring site; drift is logged, never corrected. `ProcessedTradeRepository` evicts in-memory after 24h (`processed_trade_repository.py:358`) → a WS redelivery after 24h uptime re-applies → double position. | `application/oms/reconciliation_service.py`, `brokers/upstox/broker.py:140`, `processed_trade_repository.py:358` | Confirmed real-money double-position path (Wave 1 found the eviction; Wave 2 confirmed reconciliation won't catch it). |
| P0-I | **`connect()` never wires the runtime kernel** (quota/router/stream-orchestrator). Public live trading runs with **zero quota throttling** → broker rate-limit ban risk; multi-broker routing/failover absent. | `tradex/session.py:62-133` vs `runtime/infrastructure.py:77` | The "honest kernel" is dead for the public API. |
| P0-J | **Client chooses the live broker via query param.** `POST /orders` takes `broker=Query("paper")` → anyone with a key can route real money to dhan/upstox. | `api/routers/orders.py:259` | Order routing decided by client input, not server policy. |
| P0-K | **Global kill-switch toggled by any API key.** `POST /risk/kill-switch` reachable by any valid key, no role distinction. | `api/routers/risk.py:27`, `api/routers/live/extended.py:315` | Any consumer can halt/re-enable all trading. |

---

## 1. Composition Root (`tradex/runtime`) — Split Root, Weaker Public Half

- `tradex.connect()` builds gateway→data→exec→OMS **in isolation**; it never calls `build_infrastructure`
  (`runtime/infrastructure.py:77`), so `BrokerRouter`/`QuotaScheduler`/`StreamOrchestrator`/`HistoricalDataCoordinator`
  are never instantiated for the public API. **Quota throttling is dead** (`quota_scheduler.py` never
  instantiated by `connect`) → rate-limit ban risk.
- **Global-mutable broker registry via import side-effect** (`adapter_factory.py:25-103`): importing
  `brokers.dhan` populates module-level dicts. Import order silently changes selectable providers.
- `create_gateway` fails *soft* (returns `None`, `gateway_factory.py:107`); `open_session` can build a
  `DomainSession` on a dead gateway → silent no-trading.
- `GatewayExecutionProvider.place_order` (`gateway_execution.py:55`) catches broad `TypeError` and retries →
  **double-submit risk** if the first call hit the wire.
- `StreamOrchestrator` does blocking `sleep` inside async reconnect (`:619-638`) and swaps `broker_id` via
  `object.__setattr__` (`:741`); order delivery awaited with **no timeout** (`:357`).
- TLS hardening (`ssl_hardening.create_pinned_session`) is **never called** by `connection_pool.py:154` →
  advertised security is decorative.
- **`brokers/common/*` is entirely re-export shims** of `tradex/runtime/*` — dead compat facade; delete it.
- **Verdict:** `connect()` yields an internally-consistent OMS spine but is the *weaker* half of a split
  root. Consolidate on `build_infrastructure` as the single root.

## 2. Security & Auth — Not Ready for Real Money

- **P0-B/P0-C above.** Plus:
- Token state stored **plaintext at rest by default** (`encrypted_token_state_store.py:59` degrades to
  plaintext JSON when `SECRET_ENCRYPTION_KEY` unset; `token.py:196` writes refresh tokens in cleartext).
- Swagger/OpenAPI public without auth in prod (`api/auth.py:68` includes `/docs`,`/redoc`,`/openapi.json`).
- WS API key read from query string (`api/auth.py:112`) → lands in proxy/access logs.
- `CredentialValidator` is **presence-only** (`credential_validator.py:23`); a 1-char token passes. Accepts
  unknown broker names (skips validation).
- `load_env_file` (`environment_bootstrap.py:75`) overwrites `os.environ` unconditionally — a stray file key
  clobbers an injected secret silently.
- Runtime order path IS fail-closed (`live_actionable` gate, capital fn→`Decimal(0)`, `allow_live_orders`
  default-off, constant-time key compare). Two structural defects (tracked creds + fail-open API auth)
  defeat that.
- **Secrets hygiene checklist before live:** gitignore+scrub `.env.local`, rotate keys, mandatory
  `SECRET_ENCRYPTION_KEY`, durable audit, deny-by-default `AUTH_MODE`, format-validate creds.

## 3. REST API Surface — Not Safe to Expose

- **P0-A (won't boot), P0-J (client-chosen broker), P0-K (kill-switch by any key).** Plus:
- Core market-data endpoints (`/market/quote`, `/live/quote|ltp|depth|candles`) **always 503 in prod** —
  `market.set_session` is never called at startup (`api/routers/market.py:32` vs `runtime/api_bootstrap.py`
  no call). Feature is test-only.
- `live/orders.py`, `live/portfolio.py`, `live/derivatives.py` read **straight from the broker gateway**,
  bypassing OMS/domain → `GET /orders` (OMS) and `GET /live/orders` (gateway) can disagree (parity violation).
- `live/extended.py:152,168,204,237` probe private `gw._conn`/`_broker`/`_broker.portfolio`/`_broker.static_ip`
  → infra/secret leakage, brittle. `live/health.py` returns `gw.describe()`/`capabilities()` verbatim.
- `v2/domain_endpoints.py` is the clean domain-only pattern but is **never mounted** (dead code).
- No shutdown flush of in-flight orders (`api/main.py:134`); no request body-size limit; error details leak
  broker strings to clients (`orders.py:140`, `market.py:210`).
- **`trigger_price` dropped on SL orders** (`orders.py:290-300`) → stop orders placed without trigger →
  invalid/rejected.
- **Verdict:** mount `v2` as canonical, redirect live routers to OMS/domain, server-side broker selection,
  role-scoped control-plane, shutdown reconciliation, opaque errors, fix `validate_production_config`.

## 4. Market Data / Config / Datalake — Replay-Incompatible

- **P0-D (UTC vs IST).** Plus:
- **Three divergent config systems** (`config/schema.py:65/194/222` + `profiles/__init__.py`) can silently
  disagree on broker/env (`TRADEX_APP_ENV` vs `APP_ENV`).
- `primary_broker` not validated against which broker has live creds (`schema.py:286` + `validator.py:88`).
- **No zero/negative-price rejection** at ingestion (`validation.py:97`); `close=0` passes to indicators/backtest.
- Fragile paise→rupee heuristic (`normalize.py:78` divides by 100 if `max>100000`) → silent 100× error on mislabel.
- **Two `normalize_symbol` implementations** (`src/domain/symbols.py:19` vs `datalake/core/symbols.py:29`) →
  `RELIANCE-EQ` ≠ identity; instrument drift.
- Strong `DataQualityValidator` (`data_validator.py:97`) is **not wired into ingestion**; the weaker one is used.
- `datalake/*backtest*` confirmed ImportError tombstones (moved to `analytics`). `DataLakeGateway.quote()` is a
  degraded stub (bid=low, ask=high) — quarantine from quote/stream interfaces.
- **Verdict:** redesign required — one tz-aware normalizer, one pydantic config, one symbol normalizer, wire
  the strong validator.

## 5. Infrastructure / Reconciliation — Detects but Does Not Correct

- **P0-H above.** Plus:
- `ReconciliationService` is read-only advisory; `auto_repair=False` at every wiring site
  (`brokers/upstox/broker.py:140`, `cli/services/broker_service.py:662`, `oms_setup.py:94,204`).
- Fetch-failure → false HIGH drift every cycle (`upstox service.py:131-140` swallow errors to `[]`) → alert
  fatigue masks real drift.
- No funds/margin reconciliation (only orders/positions). MEDIUM drift never healed; `TypeError`-skip silently
  drops mismatches (`upstox service.py:77-78`).
- Health check reads cached state, never pings broker (`health_check.py:40-43`) → `/readyz` can report HEALTHY
  while REST is down → trades route to a dead broker.
- Audit in-memory by default (`application/audit.py:289`) → no durable forensic trail.
- **No messaging tier** beyond in-process event bus (single point of failure; not horizontally scalable).
- **Verdict:** fix dedup eviction immediately; make reconciliation correct-then-heal (human-gated) with full
  funds coverage; default audit to durable append-only; real health probes.

## 6. Backtest Engine Math — PnL Not Trustworthy

- **P0-E (wrong equity curves), P0-F (look-ahead fill), plus:**
- **Double slippage in PARITY mode** (`engine.py:577` pre-slips, then `oms_backtest_adapter.py:151` slips again)
  → the mode meant to match live is *less* accurate.
- **Replay shadow-capital vs OMS desync** (`engine.py:599,789`): reported PnL ≠ risk-gated reality.
- **4 commission models** (Replay FLAT/Indian; Fast raw flat×2; Paper `max(pct,flat)` exit + flat entry).
- **Multi-symbol replay duplicates capital** (`engine.py:430` seeds each symbol with full `initial_capital`)
  → nonsensical portfolio curve. Paper shares one session (so they disagree on semantics too).
- **FastBacktest ignores stops/targets** → different trade set than Replay/Paper.
- **SMA RSI/ATR used; Wilder (industry standard, in `src/domain/indicators`) is dead code** (grep: no engine
  imports it). SMA RSI crosses 30/70 ~15-30% more often → entirely different signal set.
- `min_periods=1` on trend/vol features → warmup false signals; `SwingHighLow` `center=True` leaks future.
- **Verdict:** redesign, not patch — one `PortfolioState` with correct `cash + Σ(qty×current_close)`, default
  next-bar-open fills, one cost model, one indicator library (Wilder), one shared session; gate on numeric
  zero-parity test.

## 7. Shared / Providers / Plugins / Scripts / Packaging / CI

- **Dual namespace** (`pyproject.toml:51-53` `where=["src","."]`): `domain` only resolves correctly under CI's
  pinned `PYTHONPATH`; local installs can silently import the wrong copy.
- **importlinter contracts contain GHOST module refs** (`:287-290` reference `tradex.runtime.*` which doesn't
  exist; real package is `runtime.*`) → the "Application infrastructure separation" contract is a **no-op**
  against real cross-layer `runtime` imports. Plus `shared` omitted from `root_packages`.
- **Dead duplicate packages:** `shared` (re-exports `brokers.common.broker_capabilities`), `providers/*`
  (deprecated, swallows exceptions → silent `None` data), `plugins/indicators/*` (shim re-exports). Delete all.
- **Empty broker entry-point group** (`pyproject.toml:45-49` commented out) → no plugin discovery; `plugins/` dead.
- `verify_deps.py:9` reads non-existent `requirements.txt` → broken (raises `FileNotFoundError`).
- **Non-blocking mypy/bandit/safety** (`|| true`), integration/Upstox only on `main`, **no mutation / pre-prod /
  live-orders gate** despite declared markers → zero-parity rule unenforced in CI.
- `runtime/` is both a code package AND holds `server.log` (53 MB), `dead_letter.sqlite`, `*.lock`,
  `*-token-state.json` → artifact pollution in an importable path.
- **Verdict:** #1 fix = collapse dual namespace to `where=["src"]`, relocate root pkgs under `src/`, fix
  importlinter to reference real `runtime.*` + add `shared`; delete dead packages; make security gates blocking.

## 8. Execution Seam — The Money Hole is the Composer

- **P0-G above.** Path inventory (guarantees: Idempotency/Risk/Kill-switch/Audit):
  - SDK `buy` → OMS ✅✅✅✅
  - Live Orchestrator → OMS ✅✅✅✅
  - ExecutionService → OMS ✅✅✅✅
  - Replay-via-OMS ✅✅✅✅
  - CLI `place-order` → OMS ✅✅✅✅
  - **CLI `place-orders`/`cancel`/`modify` → ExecutionComposer ❌❌⚠️(no risk_manager)❌**
  - **ExecutionComposer direct ❌❌⚠️❌**
  - **Replay PURE_SIM (`allow_simulate_without_oms=True`) ❌❌❌❌**
- `submission_pipeline.py` is NOT a third stack (it's a payload builder inside gateways). The fork is the
  Composer bypassing `OrderManager`.
- **Verdict:** `OrderManager.place_order(OmsOrderCommand, submit_fn)` is the ONE spine. Composer becomes a thin
  adapter that builds `OmsOrderCommand` + injects mandatory `risk_manager`/`audit_logger`. PURE_SIM extracted to
  a research-only engine, never sharing the production `ReplayEngine` entry point.

---

## 9. Consolidated "Cannot Trade Real Money Until" Gate (all P0)

1. P0-A — API boots (`validate_production_config` resolves / removed).
2. P0-B — `.env.local` out of git + history scrubbed + keys rotated.
3. P0-C — `AUTH_MODE` deny-by-default; docs gated.
4. P0-D — single UTC tz-aware normalizer (kills 5h30m backtest shift).
5. P0-E/F — one correct equity curve + next-bar-open fills (trustworthy PnL).
6. P0-G — Composer collapsed onto OMS (kill-switch/risk/idempotency/audit on every order).
7. P0-H — durable dedup ledger (no 24h eviction) + reconciliation heals.
8. P0-I — `connect()` wires quota/router/stream kernel.
9. P0-J — server-side broker selection (not client query param).
10. P0-K — role-scoped kill-switch.

Plus the Wave-1 P0s (live never runs indicators; two event buses; trade-before-order race; Wilder-vs-SMA RSI;
duplicate backtest/scanner engines).

---

*Part 2 of the Architecture Review Board output. 8 parallel read-only agents, file:line-verified.
Appends to `docs/INSTITUTIONAL_ARCHITECTURE_REDESIGN.md` (Part 1). No code modified.*
