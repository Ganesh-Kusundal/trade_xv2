# ARCHITECTURE FINDINGS DOCUMENT — STAGE 1 (Loop Iteration 1)

**Authors:** AGENT 1 (PRINCIPAL ARCHITECT), three parallel deep reviews
**Covers:** Terminal Conditions T1 (repo organisation), T2 (architecture sound), T3 (EDA honest)
**Method:** Read-only; claims cross-checked against filesystem + `git ls-files` + `uv run lint-imports`
**Status:** VERIFIED by AGENT 6 (no blocking objections). STAGE 1 deliverable accepted; T1/T2/T3 remain NOT MET pending fix/verify cycles.

> All evidence is file:line. Findings are consolidated from three parallel reviews; a single contradictory claim (T1 #7 "split-brain OMS") was resolved by reading the file — `brokers/common/oms/_internal/reentrancy_guard.py` is a deprecated one-line shim re-exporting from `application.oms._internal.reentrancy_guard` (T2 finding correct; OMS duplication is RESOLVED, not outstanding).

---

## 0. System Snapshot

| Layer | .py | Role | Layer-health |
|---|---|---|---|
| domain | 63 | entities, value objects, ports, events — innermost | 🟢 clean except `pandas` in 2 ports |
| brokers | 484 | dhan/upstox/paper adapters + `brokers/common` (165 .py) | 🟡 adapters OK; `common` is a God module that "knows" broker ids |
| infrastructure | 27 | event_bus, event_log, lifecycle, observability, security | 🟢 healthiest context |
| application | 73 | oms, execution, trading, composer | 🟡 fat `place_order` (138 LoC), fat `TradingContext` (772 LoC) |
| datalake | 129 | parquet/duckdb storage + scanner + research | 🟡 leaks `brokers.common.batch_executor` |
| market_data | 0 | 3.7 GB data dir (parquet/duckdb/sqlite) — NOT a code package | 🔴 org gap |
| analytics | 128 | backtest, scanner, replay, views | 🟡 `ViewManager` has duplicate method defs |
| api | 37 | FastAPI routers + ws bridge | 🟢 |
| cli | 121 | commands, services, widgets, views | 🔴 imports broker adapters at top-level |
| config | 16 | endpoints, indices, secrets_manager, schema | 🟢 absorbed root orphans |
| frontend | 32 ts | React/Vite UI | 🔴 node_modules committed (5635 files) |
| runtime | 7 py | composition root (untracked!) | 🔴 entire dir excluded from VCS |

`uv run lint-imports` → **PASS** (exit 0). All 11 declared import-linter contracts green. But the declared contract set is **weaker than the intended layer contract** (see §2 below).

---

## 1. Module Map (T1)

See AGENT-1 T1 report for the full 14-row table. Headline ownership verdicts:
- 🟢 Clean ownership: `domain`, `infrastructure`, `application`(code), `analytics`, `api`, `config`, `datalake`(internal).
- 🟡 Loose / god-package: `brokers/common` (165 .py / 55 dirs), `datalake` top-level (~30 loose modules incl. duplicate `symbols.py`/`normalize.py`), `scripts` (26 flat .py).
- 🔴 Organisation failure: `market_data/` (data masquerading as code pkg), root orphan .py (`endpoints.py`, `indices.py`, `secrets_manager.py`, `api_server.py`, `conftest.py`, `tradex`), 23 root `.md` docs, `runtime/` untracked source, `frontend/node_modules` committed, stray binary (`:memory:`, 4 jpg, download.png).

---

## 2. Dependency Rule Verification (T1 + T2)

**Declared contracts (`.import-linter.ini`): 11 `forbidden` contracts. `uv run lint-imports` PASS.** Independent AST/grep cross-checks confirm **zero real violations** of the declared set (all apparent hits are inside docstring `Usage:` blocks or whitelisted test files).

**Critical gaps — the declared contract set does not enforce the intended layer contract:**

| Missing contract | Why needed | Real-world leak it lets through |
|---|---|---|
| `forbidden: domain → {brokers,application,infrastructure,cli,analytics,api,datalake,config,runtime,market_data}` | domain isolation rests only on `tests/architecture/test_domain_single_source.py` (a single-layer defence). | a future `domain/foo.py: from brokers.common.core.domain import ...` would pass `lint-imports`. |
| `forbidden: cli → brokers.{dhan,upstox,paper}` | goal.md Phase-1 says CLI must not import broker adapters. | `cli/commands/cache_management.py:22` `from brokers.dhan.loader import InstrumentLoader`; `cli/services/broker_registry.py:268-306` factory dispatch lives in CLI tier. |
| `forbidden: brokers.common → brokers.{dhan,upstox,paper} capability factories` (extends existing `brokers-common-independence`) | common must remain broker-agnostic. | `brokers/common/adapters/market_data_gateway_adapter.py:33-37` literal `_CAPABILITY_FACTORIES={"dhan":dhan_capabilities,"upstox":upstox_capabilities}`; `brokers/common/capabilities.py:235,336` defines `dhan_capabilities()`/`upstox_capabilities()` *inside common*. |
| `forbidden: datalake → brokers.common.batch_executor` | datalake must not depend on broker layer. | `datalake/ingestion/loader.py:31`, `datalake/ingestion/updater.py:13` import `brokers.common.batch_executor.batch_execute`. |

`config`, `runtime`, `tests`, `scripts`, `market_data`, `frontend` are **not in `root_packages`** and so are not linted at all.

---

## 3. Domain Boundary Assessment (T2)

- Domain is **import-pure** w.r.t. brokers/application/infrastructure/etc. ✅ (verified by grep; sole `infrastructure.event_bus` hit at `domain/ports/event_publisher.py:19` is inside a docstring).
- 🟡 **`pandas` leaks into domain ports**: `domain/ports/market_data.py:8`, `domain/ports/strategy_evaluator.py:7` import `pandas` and expose `pd.DataFrame` in the port contract — a *transport* concern in the innermost layer. Fix: return `Iterable[Bar]` / a frozen `BarsRecord`; produce DataFrames at the broker boundary.
- 🟡 `domain/constants/` mixes operational config (timeouts, resilience defaults) with business invariants. Move tunables to `config/`.

---

## 4. Bounded Context Assessment (T2)

| Context | Leaks IN | Leaks OUT | Verdict |
|---|---|---|---|
| domain | `pandas` in 2 ports | none of consequence | 🟢 mostly clean |
| brokers/common | — | 🔴 **hardcodes broker-id literals** `"dhan"`/`"upstox"` in ≥7 modules; **defines `dhan_capabilities()`/`upstox_capabilities()` inside common**; `_CAPABILITY_FACTORIES` literal-keyed dispatch | 🔴 not broker-agnostic |
| brokers/dhan & upstox | none to domain; none to each other (contract green) | 🟡 import `from endpoints import Dhan` via root shim (`dhan/settings.py:31`, `http_client.py:17`, `loader.py:14`); fat files (`orders.py` 771, `gateway.py` 685/791, `market_feed.py` 746, `depth_feed_base.py` 693, `upstox/mappers/domain_mapper.py` 562) | 🟡 |
| brokers/paper | none | used as test double in application/cli tests (correct; covered by ignore-imports) | 🟢 |
| market_data | (not code) | n/a | 🔴 org gap |
| datalake | none of broker *adapters* | 🔴 uses `brokers.common.batch_executor`; ~30 loose top-level modules with duplicate `symbols.py`/`normalize.py` | 🟡 |
| analytics | zero broker imports (clean) | 🟠 `analytics/views/manager.py` `ViewManager` has **duplicate method definitions** in one class (`query`, `query_df`, `query_scalar`, `view_exists`, `table_exists`, `list_views`, `view_count`, `materialize`, `register_materialized`, `drop_materialized` — each defined twice; second silently shadows first) | 🟠 god object + bug |
| application | production code clean | 🟠 `application/oms/order_manager.py:211` `place_order` ~138 LoC (idempotency+risk+event+transport+audit interleave); `application/oms/context.py:772` `TradingContext` wires 8 concerns; `application/__init__.py` `__all__=[]` | 🟠 |
| infrastructure | clean (contracts green) | — | 🟢 |
| api | all broker imports are `brokers.common.*`; routers cleanly under `api/routers/` | — | 🟢 |
| cli | — | 🔴 `cache_management.py:22` imports `brokers.dhan.loader`; factory dispatch in `cli/services/broker_registry.py:268-306` should live in `runtime/` | 🔴 |

---

## 5. Architectural Anti-Patterns (T2 + T4 preview)

- **God packages:** `brokers/common` (165 .py / 55 dirs); `datalake` top-level (~30 loose modules).
- **God classes:** `analytics/views/manager.py:769` (ViewManager, *duplicate methods*); `brokers/common/stream_orchestrator.py:803`; `application/oms/context.py:772` (TradingContext); `domain/capability_manifest.py:1240` (data catalogue, acceptable but splittable); `brokers/common/historical_coordinator.py:689`; `cli/services/broker_service.py:559`.
- **Fat method:** `OrderManager.place_order` (`application/oms/order_manager.py:211-349`, 139 lines).
- **Duplicate method defs in one class:** `analytics/views/manager.py` `ViewManager` (line pairs 90–138 vs 144–716) — real bug.
- **Leaky abstraction via re-export:** `brokers/dhan/domain.py:18-27` `__getattr__` silently re-exports canonical `domain` types — ownership unreadable.
- **Static singleton:** `brokers/common/connection_pool.py:238-301` `get_connection_pool()` — module-level singleton; undocumented.
- **Circular-deps via root shims:** previously broken by shims forwarding to `config.*`; residual = broker still imports by orphan name `endpoints`. ✅ mostly resolved.

---

## 6. Gateway / Routing Design Pre-findings (T6 hand-off for Stage 2)

The **interface and provenance** design is *architecturally sound*; the **wiring** is dishonest.

- **Honest capability interface:** `brokers/common/gateway_interfaces.py:30-120` 8 narrow ISP interfaces; `brokers/common/gateway.py:44-57` `MarketDataGateway` composes them; "No broker-specific fields are allowed in return types" (`gateway.py:39-46`).
- **Execution/data separation:** `brokers/common/policy.py:18-22` "execution account must match broker used for place_order; market-data and execution accounts are independent"; `brokers/common/models.py:22-65` `OperationKind.is_execution()` vs `is_market_data()`.
- **Source provenance:** `brokers/common/provenance.py:24-50` `ChunkRecord`/`BarRangeRecord` carry `broker_id`; `brokers/common/historical_coordinator.py:22-26` invariant: coordinator calls only `CommonBrokerGateway.get_historical_bars()`.
- **Router:** `brokers/common/router.py:46-100` deterministic `BrokerRouter.route()` (capability → health → quota headroom scoring → structured `routing.decision` event). Sound.
- **Dishonest wiring (T6 blockers):**
  - `brokers/common/adapters/market_data_gateway_adapter.py:40-44` `_CAPABILITY_FACTORIES` literal-keyed dict.
  - `brokers/common/capabilities.py:235,336` `dhan_capabilities()`/`upstox_capabilities()` defined *inside common*.
  - `brokers/common/policy_defaults.py:43-179` ≥22 broker-id literals.
  - `brokers/common/intelligent_market_gateway.py:79` `primary_broker: str = "dhan"` default — defaults belong in a policy/profile, not the gateway class.
  - `brokers/common/connection_pool.py:42` `BROKER_TYPES={"upstox","dhan","paper"}` literal set.

Hand-off points for Stage 2: G1–G10 listed in the AGENT-1 T2 report (gateway/router/policy/composer/OMS-proxy locations).

---

## 7. Event-Driven Architecture Assessment (T3)

Event system relocated correctly to `infrastructure/event_bus` + `infrastructure/event_log` + `domain/events/types.py` + `domain/ports/event_publisher.py` (the `brokers.common.event_bus` contract forbids the legacy import — verified green).

**Honest parts:**
- 🟢 `DomainEvent` is `@dataclass(frozen=True)` (`infrastructure/event_bus/event_bus.py:44`); `__post_init__` rejects naive tz (`event_bus.py:62-70`); immutability asserted for all 8 fields (`tests/test_domain_event_immutability.py:31-93`).
- 🟢 `_prepare_event` uses `dataclasses.replace()` (never `object.__setattr__`) to inject `correlation_id`/`sequence_number` (`event_bus.py:325-355`); original untouched by `publish()` (`test_domain_event_immutability.py:101-155`).
- 🟢 Persistence-before-dispatch (`event_bus.py:383-406`); handler failures are dead-lettered, never swallowed (`event_bus.py:430-465`); dedicated `replay_mode` disables auto-persistence + dispatch and preserves `sequence_number` (`event_bus.py:194,345-349,407-411`).
- 🟢 Ordering via `sequence_number` (monotonic `itertools.count`); replay total order `(timestamp, sequence)` (`analytics/replay/orchestrator.py:86-89`).

**Defects (state-safety):**

| # | Severity | Defect | Evidence |
|---|---|---|---|
| E1 | 🔴 Critical | Replayed events never reach OMS handlers. `UnifiedReplayOrchestrator` builds `EventBus(replay_mode=True)` then publishes each event — but `replay_mode` short-circuits dispatch *before* handlers (`event_bus.py:407-411`). The engine only processes bars; the "replay events through OMS" path is dead code. | `analytics/replay/orchestrator.py:213-218,389-391` ↔ `event_bus.py:407-411` |
| E2 | 🔴 Critical | `event_id` not persisted on the production (buffered) path and not restored on replay. `BufferedEventLog.append` JSONL record omits `event_id` (`event_log.py:353-361`); `EventLog.replay` reconstructs `DomainEvent(...)` without event_id (`event_log.py:251-259`) → fresh uuid → idempotency-by-event_id broken on restart. | `infrastructure/event_log.py:251-259,353-361` |
| E3 | 🔴 Critical | Enum fields not reconstructed on deserialization. `_deserialize_payload` calls `_deserialize_value(v)` with `expected_type=None` (`event_log.py:109-111`); `_deserialize_value` only rehydrates Enums when `expected_type` is provided (`event_log.py:72-81`). Result: rehydrated `Order.status`/`side`/`order_type`/`product_type`/`validity` & `Trade.side`/`product_type` come back as raw `str`; `OrderStatus.is_terminal` access (`order_manager.py:545`) crashes during OMS replay. | `infrastructure/event_log.py:72-81,109-111` |
| E4 | 🔴 Critical | State mutations without events. `RiskManager.set_kill_switch` (called from `order_manager.py:510`, `context.py:510,705`) and `DailyPnlResetScheduler` mutate manager state but **never publish** the catalog events `KILL_SWITCH_FLIPPED`/`DAILY_PNL_RESET` (orphan types `types.py:80,99`). `PositionManager.update_ltp` (`position_manager.py:161-170`) mutates positions (and unrealized/realized PnL) with **no event at all** → such state is not reconstructable from the event log. | `application/oms/risk_manager`, `application/oms/position_manager.py:161-170`, `daily_pnl_reset_scheduler.py` |
| E5 | 🟠 High | `BufferedEventLog` failure semantics silently swallow exceptions. `_flush_locked` catches `Exception`, logs, does not re-raise, does not increment `append_errors` (`event_log.py:405-407`) — contradicts base "never silent" contract (`event_log.py:120-122,198-207`) and bus dead-lettering. Also `BufferedEventLog.append` overrides `EventLog.append` **dropping the `_seen_ids` idempotency guard** (`event_log.py:173-176` vs `:341`) → duplicate `TRADE` events persisted twice on the production path. | `infrastructure/event_log.py:341-407` |
| E6 | 🟠 High | Scanner `publish()` called with wrong signature. `analytics/scanner/models.py:153,217,236` pass `(str, payload=...)` to `EventBus.publish` which takes a single `DomainEvent` (`event_bus.py:359`). On a real bus this raises `AttributeError`; call sites are unprotected by try/except → entire scan aborts and scanner events are never logged → candidate stream is unreplayable. | `analytics/scanner/models.py:153,217,236` |
| E7 | 🟠 High | Payload/contract drift unenforced. Multiple events publish payloads that mismatch the documented `EVENT_PAYLOADS` contract: `TICK` `{"quote": Quote}` vs contract `ltp/open/...`; `DEPTH` `{"depth": MarketDepth}` vs `bids/asks`; `ORDER_CANCELLED` `{"order": Order}` vs `order_id`; `ORDER_REJECTED` `{"order,reason"}` vs `order_id,reason`; `POSITION_UPDATED` `{"position": Position}` vs `symbol,quantity,avg_price`; `SIGNAL_GENERATED` `{"symbol,strategy,...}` vs `signal`. `make_payload(validate=False)` is the default (`types.py:394-422`) → contract never enforced. | many (see T3 report) |
| E8 | 🟠 High | Replay state assertion only checks trade count. `UnifiedReplayResult._assert_state` (`orchestrator.py:413-473`) does not assert positions / avg price / realized PnL / equity → a divergent replay silently passes. | `analytics/replay/orchestrator.py:413-473` |
| E9 | 🟡 Medium | Inter-handler payload isolation not guaranteed. `DomainEvent.now` does `dict(payload)` — shallow copy (`event_bus.py:104`); inner objects shared by reference; a handler mutating `event.payload["x"]` is visible to the next handler (`test_domain_event_immutability.py:378-398` documents the leak). Live domain objects (`Order/Trade/Position` are themselves frozen, but the payload dict is not). | `event_bus.py:104` |
| E10 | 🟡 Medium | Non-canonical event types bypass the catalogue. `PORTFOLIO_STREAM`, `HOLDING_UPDATED`, `GTT_UPDATED` (`brokers/upstox/websocket/portfolio_stream.py:204,210,213`) and `QUOTE` (`api/ws/bridge.py:53`) are not in `EventType` (`domain/events/types.py:44-141`). | as cited |
| E11 | 🟡 Medium | Mutable containers inside frozen DTOs. `SignalDTO.metadata: dict|None`, `CandidateDTO.metrics: dict`, `reasons: list` (`domain/models/trading.py:17,37`) shared by reference on `SIGNAL_EXECUTED` replay → broken determinism. | `domain/models/trading.py` |
| E12 | 🟡 Low | Orphan event types. ≥20 `EventType` members have no publisher anywhere in production (`POSITION_CHANGED`, `RISK_BREACH`, `RISK_VIOLATED`, `DRAWDOWN_LIMIT_HIT`, `BROKER_CONNECTED/DISCONNECTED`, `TOKEN_REFRESHED/EXPIRED`, `CIRCUIT_BREAKER_OPENED/CLOSED`, `SERVICE_STARTED/STOPPED/FAILED`, `HEALTH_CHECK_*`, `STRATEGY_ACTIVATED/PAUSED/DISABLED`, `SCANNER_STATE_CHANGED`, `PORTFOLIO_UPDATED`, `METRICS_UPDATED`, `RECONCILIATION_DRIFT/OK`, `INDEX_QUOTE`, `OPTION_CHAIN`, `ORDER_SUBMITTED`). Catalogue does not reflect reality. | `domain/events/types.py` |

---

## 8. Ordered Prescription List (consolidated, ranked by severity)

> P0 = blocks the terminal condition; P1 = high-impact; P2 = coherence/maintenance.

### P0 — Security & VCS integrity (blocks T1) — owner: AGENT 5 (security) + AGENT 2
1. **Rotate + purge `.env.local`.** It is `git ls-files`-tracked and populated with live `DHAN_*`/`UPSTOX_*` secrets. `git rm --cached .env.local`, rotate all creds, history-purge via BFG/`git filter-repo`. (`.gitignore:3` already lists it; tracked files ignore gitignore.)
2. **Stop gitignoring `runtime/` source.** `.gitignore:32` excludes whole dir; `git ls-files runtime` = 0. Force-add `runtime/__init__.py`, `api_bootstrap.py`, `broker_runtime.py`, `composition.py`, `trading_runtime_factory.py`, `production_config.py`, `parity_gate.py`; keep `runtime/*.json`, `*.sqlite`, `event-log/`, `__pycache__/` ignored. Add `runtime` to import-linter `root_packages`.
3. **Untrack `frontend/node_modules/`** (5635 tracked files). `git rm -r --cached frontend/node_modules`; add to `.gitignore`.
4. **Untrack/relocate root binary junk** (`:memory:`, 4 `.jpg`, `download.png`).

### P0 — Boundary enforcement (blocks T2) — owner: AGENT 2
5. **Remove broker-id knowledge from `brokers/common`.** Move `dhan_capabilities()`/`upstox_capabilities()` (`brokers/common/capabilities.py:235,336`) into the adapter packages; replace literal `_CAPABILITY_FACTORIES` dict (`adapters/market_data_gateway_adapter.py:40-44`) with adapter-contributed registration; replace literal `"dhan"`/`"upstox"` candidate lists in `policy_defaults.py:43-179`, `policy.py:132-212` with broker-agnostic `RoutingProfileRegistry`; remove `BROKER_TYPES` literal set from `connection_pool.py:42`; remove `primary_broker="dhan"` default from `intelligent_market_gateway.py:79`.
6. **Add the missing import-linter contracts and enforce in CI:** (a) `domain → {outer layers}`; (b) `cli → brokers.{dhan,upstox,paper}`; (c) extend `brokers-common-independence` to forbid `brokers.common` importing `brokers.{dhan,upstox,paper}`'s capability factories; (d) `datalake → brokers.common.batch_executor`; (e) add `config`, `runtime`, `tests`, `scripts` to `root_packages`.
7. **Stop CLI commands importing broker adapters.** Rewrite `cli/commands/cache_management.py:22` through `BrokerService`; rewrite `cli/commands/market.py:19` to `from config.indices import INDEX_SYMBOLS`; relocate factory dispatch `cli/services/broker_registry.py:268-306` to `runtime/broker_runtime.py`.
8. **Decouple `datalake/ingestion` from `brokers.common`.** Promote `batch_executor` to a shared `infrastructure/concurrency` module, or duplicate the ~30-line helper into `datalake`.

### P0 — EDA correctness/replayability (blocks T3) — owner: AGENT 2 (with AGENT 3 tests)
9. **Fix replay dispatch path (E1).** Route replay through a live-dispatch bus for the engine's bus subscription (separate "ingest bus" vs "engine bus"), or invoke OMS handlers directly (mirroring `TradingContext._replay_log_into_oms`, `context.py:438-451`).
10. **Persist + restore `event_id` (E2).** Add `event_id` to `BufferedEventLog.append` JSONL record; `EventLog.replay` must reconstruct `DomainEvent` with the stored `event_id`.
11. **Fix Enum deserialization (E3).** Thread `typing.get_type_hints(cls)` into `_deserialize_value` for each field, or add `to_dict`/`from_dict` to `Order/Trade/Position`.
12. **Emit events for every state transition (E4).** Publish `KILL_SWITCH_FLIPPED`, `DAILY_PNL_RESET`; emit a `POSITION_UPDATED` (or scoped `LTP_UPDATED`) on `PositionManager.update_ltp` — or explicitly downgrade the replayability claim by documenting that the log is a notification channel, not a source-of-truth.

### P1 — High-impact structural
13. **Strip `pandas` from domain ports** (`domain/ports/market_data.py:8`, `strategy_evaluator.py:7`).
14. **Fix `ViewManager` duplicate method definitions** (`analytics/views/manager.py`); split into `ViewCatalog` + `MaterializationRunner`.
15. **Decompose `OrderManager.place_order`** (138 LoC) into ≤50 LoC orchestration over `_internal/` collaborators.
16. **Trim `TradingContext`** (772 LoC) into a thin container; extract `ReconciliationWiring`/`DlqMonitorWiring`/`SignalHandlerWiring`.
17. **`BufferedEventLog` non-silent failures (E5).** Re-raise `OSError/ValueError` to dead-letter; increment `append_errors`; re-add `_seen_ids` idempotency guard on the override.
18. **Fix scanner `publish()` signature (E6).** `DomainEvent.now(EventType.X.value, payload=..., source=...)` then `bus.publish(event)`.
19. **Enforce payload contract (E7).** `make_payload(validate=True)` at publishers; publish plain snapshot dicts matching `EVENT_PAYLOADS`, not live objects.
20. **Deepen replay state assertion (E8)** — positions, avg price, realized PnL, equity.
21. **Decompose `brokers/common` God module** into `brokers/core/` + `brokers/shared/`; each surviving subpackage `__init__.py` declares `__all__`.

### P2 — Coherence / naming / cosmetics
22. **Delete root-orphan shims** after migrating call sites (`endpoints.py`, `indices.py`, `secrets_manager.py` → `config.*`; `api_server.py` → `cli/commands/serve.py` or pyproject entry-point; root `conftest.py`'s `_ensure_dhanhq_sdk_aliases` shim → `brokers/dhan/tests/conftest.py`).
23. **Move 23 root `.md` reports into `docs/`** (audits/history/adr).
24. **Resolve `market_data/` vs `datalake/` vs `data/`** — `market_data/` is 3.7 GB data, not a code package; relocate under `datalake/store/` or out-of-tree.
25. **Add `__all__`** to `application/__init__.py` and the ~30 empty `brokers/**/__init__.py`.
26. **Categorise `scripts/`** into `ci/`, `diagnostics/`, `tools/`, `test/`.
27. **Make inter-handler payload isolation real (E9)** — deep-serialize inner live objects on publish, or freeze via `MappingProxyType`.
28. **Add/catalogue non-canonical event types (E10)** — `PORTFOLIO_STREAM`, `HOLDING_UPDATED`, `GTT_UPDATED`, `QUOTE`, or normalise streams to canonical types.
29. **Deep-freeze mutable DTO containers (E11)** — `SignalDTO.metadata`, `CandidateDTO.metrics/reasons` → `MappingProxyType`/`tuple`.
30. **Prune or implement orphan event types (E12)** — delete unwired `EventType` members so the catalogue reflects production reality; implement publishers at rightful call sites where the event is intended (circuit breaker, kill switch, reconciliation drift, broker reconnect, health checks).
31. **Reconcile `dhan/domain.py` `__getattr__` re-export** — replace with explicit imports so ownership is readable.
32. **Define a test-location convention** in `CONTRIBUTING.md` (co-located `*/tests/` for module-owned, central `tests/` for cross-cutting).

---

## 9. Terminal-Condition Verdict (this document)

| ID | Condition | Verdict from this document | Blockers (count) |
|---|---|---|---|
| T1 | Repository organized | **NOT MET** | 4 P0 (security/VCS/org) |
| T2 | Architecture sound, deps respected, domain isolated | **NOT MET** | 4 P0 (boundary); 5 P1 structural |
| T3 | EDA honest (correct, state-safe, replayable) | **NOT MET** | 4 P0 (E1–E4); 5 P1 (E5–E8, anti-patterns) |

This document satisfies the STAGE 1 *deliverable* (module map, dependency rule violations, domain boundary assessment, EDA event catalog, ordered prescription list). The terminal conditions themselves are not yet satisfied — they require the Stage-prescribed fix/verify cycles.