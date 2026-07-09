# Architecture Review Board — Institutional Trading Framework

**Date:** 2026-07-09  
**Branch:** `refactor/brokers-consolidation` @ `a70f1eb`  
**Corpus:** ~1,628 Python modules · ~80k prod LOC (excl. venv) · 28k graph nodes  
**Method:** Multi-perspective challenge (DDD, OMS/EMS, exchange connectivity, HPC, event systems, DX). Live AST dependency scan + graphify + source inspection. Prior docs treated as *hypotheses*, not truth.

---

## 0. Executive Council Verdict

| Dimension | Grade | One-line verdict |
|-----------|-------|------------------|
| Domain purity | **B+** | Domain no longer imports infrastructure/brokers; ports are real. Still polluted by pandas + plugin indicators. |
| Object model (Instrument-first) | **B** | `Instrument` / `Equity` / `Option` exist and are the right spine. Incomplete behaviour, dual homes, stub methods. |
| Dependency direction | **B** | Top-level domain is clean. Residual: `domain → plugins`, `datalake ↔ analytics`, CLI → concrete brokers. |
| Broker isolation | **B** | Registry + self-registration is correct. Still two physical homes (`tradex.runtime` + fat `brokers.common` residual). |
| OMS / execution spine | **B-** | Canonical OMS in `application/oms` with ports. Ghost twin in `brokers/common/oms` (tests + margin). |
| Event architecture | **B-** | Typed domain events exist; bus lives in infrastructure; not all state transitions emit domain events. |
| Market-data ownership | **C+** | No single Market Data Runtime owner. Normalization triplicated. |
| SDK / DX | **C+** | `tradex.Session` exists; only paper is first-class without injected gateway. Gateway names still leak. |
| Testability of architecture | **B** | Strong fitness suite; import-linter 8 contracts; carve-outs still document unfinished work. |
| Production readiness | **B-** | Resilience, idempotency, reconciliation present — but package topology fights operators and onboarding. |
| **Overall institutional readiness** | **B-** | *Capable trading system with institutional intent; not yet an institutional object framework.* |

**Council decision:** Do **not** rewrite. Do **not** accept “it works.” Continue the *target-driven* program already underway, but **reject** several prior design choices (decorator-stacked instruments, dual gateways as permanent API, buy() that bypasses OMS, pandas as domain type).

**Primary product promise (non-negotiable):**

```python
import tradex

session = tradex.connect("dhan")          # composition root — one call
reliance = session.equity("RELIANCE")     # domain object
print(reliance.quote.ltp)
chain = reliance.option_chain()
order = reliance.buy(qty=10, limit=2955)  # OrderIntent → OMS → ExecutionProvider
```

Users never import `brokers.*`, `aiohttp`, Redis, DuckDB, or gateway classes.

---

## 1. What Is Already Correct (do not undo)

These decisions survive board challenge:

1. **Hexagonal ports in `domain.ports`** — `DataProvider`, `ExecutionProvider`, `BrokerAdapter` as structural protocols. Correct.
2. **Instrument as primary domain object** — identity + live state + provider delegation. Correct spine (Pandas/SQLAlchemy/PyTorch analogue).
3. **Domain independence contract** — zero production imports from infrastructure/brokers into domain (except the plugins leak below). Hard-won; protect it.
4. **Broker self-registration** (D1 closed) — `brokers.common` must not name `dhan`/`upstox`. Correct.
5. **Ports no longer re-export infrastructure concretes** (D-2 closed). Correct.
6. **`tradex` public package** as user-facing namespace. Correct product direction.
7. **`tradex.runtime` as platform kernel** extracted from `brokers/common` top-level modules. Correct *direction*; incomplete *execution*.
8. **OMS in `application/oms`** with Protocol injection for events/lifecycle/metrics. Correct bounded context.
9. **Capability model + extensions** for broker superpowers (depth-20/200, forever orders). Correct *idea* (not decorator wrappers).

---

## 2. Board Challenges — Decisions We Reject or Amend

### C1. Reject: Instrument decorator stack for depth (OBJECT_MODEL_PLAN §4)

**Prior proposal:** `DhanDepth20(Instrument)` wrappers.

**Board:** Wrong. Institutional systems use **capability query + optional ports**, not nested wrappers. Wrappers break identity equality, isinstance checks, serialization, and Liskov.  
**Amend:** Keep `ExtensionManager` / capability registry. Depth-N is `session.capabilities.depth_levels` + `instrument.depth(levels=n)` routed by provider. No `Depth20Instrument` class.

### C2. Reject: `Instrument.buy()` as direct broker call

**Prior / partial current:** Session/Instrument place orders via ExecutionProvider immediately.

**Board:** OMS/EMS Architect veto. Exchange connectivity must never be the first consumer of a buy intent.  
**Amend:**

```
Instrument.buy(...) → OrderIntent (domain VO)
  → RiskPort.evaluate
  → OMS.admit (state machine)
  → ExecutionProvider.place_order
  → ExecutionReport → domain events → Position
```

Paper and live share this path. Bypass only in explicit `raw_transport` debug mode.

### C3. Amend: “One BrokerAdapter = Data + Execution”

**Challenge:** Fat protocol (ISP violation). Live data path and order path have different SLOs, auth, and failure domains.  
**Amend:** Keep `BrokerAdapter` as *optional composition* at the session boundary, but **require** segregation of `DataProvider` and `ExecutionProvider` inside. Strategies depend on narrow ports. Adapters may implement both; callers must not require both.

### C4. Reject: pandas as domain currency

**Evidence:** `instrument.py` imports `pandas`; `HistoricalSeries` re-exports DataFrames; ports return `pd.DataFrame`.  
**Board:** Domain types are `HistoricalBar` / `HistoricalSeries` / `QuoteSnapshot`. DataFrame is an **export adapter** at analytics/CLI boundary.  
**Amend:** Remove top-level `import pandas` from domain core; keep optional export methods that lazy-import pandas.

### C5. Reject: Permanent dual home `brokers.common` ⇄ `tradex.runtime`

**Evidence:** ~30 modules are re-exports; residual real code remains (auth, resilience, idempotency, services, OMS tests, objects/session).  
**Board:** Mid-migration is worse than either end state.  
**Amend:** Finish the move in one wave: *canonical* = `tradex.runtime` + `brokers/{dhan,upstox,paper}` only. Delete or shrink `brokers.common` to pure thin shims with expiry date, then delete shims.

### C6. Reject: Leaving `domain.aggregates` as permanent aliases

**Board:** Deprecation without deletion is technical debt theatre.  
**Amend:** Delete `domain.aggregates` after one release of greppable zero imports. Same for duplicate OMS test trees under `brokers/common/oms/tests`.

### C7. Amend: Target “many runtimes” diagram

**TARGET_ARCHITECTURE** lists 7 runtimes. Correct *conceptually*; wrong if each becomes a package.  
**Amend:** One `RuntimeContext` object graph; runtimes are **roles/components**, not top-level packages. Avoid `application/scanner_runtime/` sprawl.

### C8. Reject: domain indicators importing `plugins.*`

**Evidence:** `src/domain/indicators/indicators.py` imports RSI/ATR/VWAP/MACD from plugins.  
**Board:** Dependency inversion inverted. Plugins must depend on domain protocols; domain defines Indicator protocol + pure math defaults **or** indicators live only in `analytics`/`plugins` and domain stays free of them.

---

## 3. Component Review (ownership matrix)

| Component | Current home | Correct home | Action |
|-----------|--------------|--------------|--------|
| `Instrument`, `InstrumentId` | `domain/instruments` | Domain | Keep; finish behaviour; drop pandas |
| `Order` / `Position` entities | `domain/entities` | Domain | Keep single source; delete aggregate twins |
| `OrderManager`, risk, square-off | `application/oms` | Application (OMS BC) | Keep; pure fakes in unit tests |
| `brokers/common/oms/*` | Residual | **Delete / fold** | margin → application or domain port; delete test clone |
| `BrokerSession` | `brokers/common/objects` | `tradex.session` / domain universe | Merge with `tradex.Session` |
| `MarketDataGateway` name | aliases everywhere | **Retire name** | Only `BrokerAdapter` / `DataProvider` |
| Auth / token / TOTP | `brokers/common/auth` | Infrastructure or `tradex.runtime.auth` | Move under runtime kernel |
| Resilience (CB, rate limit) | `brokers/common/resilience` | `tradex.runtime.resilience` or infra | Not broker-specific domain |
| Idempotency caches | `brokers/common/idempotency` | Infrastructure | Redis/file are infra |
| Chain normalizer | `brokers/common/options` | Broker adapter boundary | One normalizer → domain VO |
| Historical coordinator | `tradex.runtime` | Market Data Runtime role | Keep kernel; not domain |
| Router / multi-broker | `tradex.runtime` | Application composition | Session-level, not domain |
| Data lake | `datalake` | Infrastructure (persistence) | Expose via DataProvider / HistoryPort only |
| Analytics engine | `analytics` | Application/Research BC | Depends on domain VOs + history port |
| Event bus impl | `infrastructure/event_bus` | Infrastructure | Domain owns event *types* only |
| DI container | `infrastructure/di` | Infrastructure | One composition root only |
| CLI / API | `cli`, `api` | Presentation | Depend on application + tradex only |
| `capability_manifest.py` (1279 LOC) | Domain | Split by capability family | Cut god file |
| `plugins/indicators` | Plugins | Plugins **or** analytics | Domain must not import |
| `providers/` top-level | Legacy | Fold into brokers/tradex | Delete after migration |
| `market_data/` (parquet only) | Data dir | Keep as data root; no Python package required if HistoryPort owns access | Document |

---

## 4. Dependency Rules (enforced truth)

```
Presentation (api, cli)
    → Application (oms, execution, trading, composer)
    → Domain (entities, instruments, ports, events, risk policy)
         ↑ implemented by
    Infrastructure + tradex.runtime + brokers/{dhan,upstox,paper} + datalake
```

**Forbidden (any severity = fail CI):**

| From | To |
|------|----|
| domain | infrastructure, brokers, analytics, datalake, api, cli, plugins, tradex |
| application | brokers.dhan, brokers.upstox, brokers.paper (registry/ports only) |
| application (prod) | infrastructure concretes (ports only; tests may use fakes) |
| tradex.runtime | brokers.dhan / upstox (registry only) |
| analytics | brokers.* |
| datalake | analytics (break cycle — datalake must not import analytics) |

**Current measured violations (AST, prod, 2026-07-09):**

- `domain → plugins`: **4** (indicators) — **active fail**
- `datalake → analytics`: **12** — **active cycle**
- `cli → brokers.dhan`: **10** — presentation leak (registry should hide)
- Application prod → infrastructure: **0** (tests still couple — acceptable short-term if fakes preferred)

---

## 5. Object Model — Target First-Class Types

Comparable to Unreal `UObject` / Pandas `DataFrame` / SQLAlchemy `Mapper` / PyTorch `nn.Module`:

```
tradex.Session                    # composition root (auth, bus, providers)
  ├── Universe                    # instrument factory / cache (single owner)
  │     └── Instrument            # ABC of market identity + behaviour
  │           ├── Equity, Index, Future, Option
  │           ├── .quote / .depth / .history / .subscribe
  │           ├── .buy/.sell → OrderIntent (not fill)
  │           └── .option_chain() → OptionChain
  ├── Portfolio                   # positions + PnL projection
  ├── Account                     # balances, margins
  └── OMS (application service)   # admits intents, owns Order aggregate lifecycle
```

**Invariants:**

1. Only `Universe` / `Session` constructs `Instrument` instances (no ad-hoc construction in strategies).
2. Quotes/depth are immutable VOs; state updates replace `InstrumentState` atomically (already present).
3. Broker-specific power is capability-gated, never type-gated.
4. Replay = same objects + `ReplayDataProvider` + simulated `ExecutionProvider`.

---

## 6. Event & State Model (minimal institutional set)

| Event | Owner | Consumer |
|-------|-------|----------|
| `QuoteChanged` | Market data adapter → Instrument | Portfolio MTM, strategies, UI |
| `DepthChanged` | Market data adapter | Orderflow analytics |
| `OrderIntentSubmitted` | Instrument/Session | OMS |
| `OrderAccepted/Rejected/Partial/Filled/Cancelled` | OMS | Portfolio, audit, UI |
| `PositionOpened/Changed/Closed` | PositionManager | Risk, analytics |
| `SessionConnected/Disconnected` | BrokerSession | lifecycle, health |
| `RiskBreach` | RiskManager | kill switch / square-off |

**Rule:** No mutable shared dicts as “events.” No silent state change without an event when OMS or Position is involved.

---

## 7. Ranked Defects (actionable)

| ID | Severity | Defect | Fix |
|----|----------|--------|-----|
| **X1** | P0 | Mid-migration dual kernel (`tradex.runtime` + fat residual `brokers.common`) | Finish relocation; expire shims |
| **X2** | P0 | `domain → plugins` indicators | Invert: plugins implement domain Indicator protocol **or** move indicators out of domain |
| **X3** | P0 | `datalake ↔ analytics` cycle | History/research ports; datalake pure storage |
| **X4** | P1 | Ghost OMS under `brokers/common/oms` | Delete clone tests; relocate margin |
| **X5** | P1 | Gateway name zoo in implementations | Rename public surface to BrokerAdapter; keep private transport |
| **X6** | P1 | `tradex.Session` incomplete for live brokers | `tradex.connect(broker, profile=)` loads credentials + registry |
| **X7** | P1 | pandas in domain core | Lazy export only |
| **X8** | P1 | `capability_manifest.py` god file | Split by capability domain |
| **X9** | P2 | `domain.aggregates` still present | Delete after zero-ref |
| **X10** | P2 | Future/Option methods return `None` stubs | Implement domain math or remove API until real |
| **X11** | P2 | CLI imports concrete dhan | CLI uses registry only |
| **X12** | P2 | Order path may skip full OMS when using Session.buy | Wire Session.buy → OMS |
| **X13** | P3 | 24 port modules | Consolidate to ~10 capability ports |
| **X14** | P3 | scripts sprawl | Productize into cli commands |
| **X15** | P3 | Duplicate broker `Instrument` in `brokers/dhan/domain.py` | Broker-local DTO only; never named Instrument |

---

## 8. Transformation Program (board-approved sequence)

**Principle:** one vertical slice green before next; shims expire; no new abstractions without deleting an old one.

### Wave A — Truth & Isolation (1–3 days)
1. Fix `domain → plugins` (X2).
2. Break `datalake → analytics` (X3).
3. Update fitness tests + import-linter to fail on these without carve-outs.
4. Refresh TECHNICAL_DEBT.md (stale D1 status).

### Wave B — Single Kernel (3–7 days)
1. Move residual `brokers/common/{auth,resilience,idempotency,services,options,objects}` → `tradex.runtime.*` or `infrastructure.*` by true ownership.
2. Delete duplicated OMS tests under `brokers/common/oms`.
3. Time-box re-export shims (deprecate module docstring + CI counter of imports).
4. `brokers/` contains only `dhan`, `upstox`, `paper` (+ thin `__init__` registry hooks).

### Wave C — Institutional Order Spine (5–10 days)
1. Introduce `OrderIntent` VO; `Instrument.buy/sell` only create intents.
2. All execution paths through `application.oms.OrderManager`.
3. Paper/live/replay parity tests on the same spine.
4. Risk before submit is mandatory (no feature flag).

### Wave D — Object Completeness (5–10 days)
1. Finish Option/Future domain behaviour (or hide stubs).
2. `tradex.connect()` for dhan/upstox/paper.
3. Universe as sole Instrument factory with cache.
4. Remove pandas from domain import graph.

### Wave E — Market Data & Analytics Boundary (ongoing)
1. Single normalizer: broker raw → domain VO.
2. Analytics consumes domain VOs + HistoryPort only.
3. ReplayDataProvider as first-class.

### Wave F — DX & Deletion (final)
1. Delete shims, aggregates, dead packages, gateway aliases.
2. One composition root documented.
3. SDK cookbook: 10 recipes, no gateway mentions.

---

## 9. What “Done” Looks Like (exit criteria)

- [ ] `lint-imports` green with **zero** ignore_imports on domain and application-prod contracts
- [ ] `grep -R "from brokers.dhan" api cli application` → empty (except tests/adapters)
- [ ] `tradex.connect("paper"|"dhan"|"upstox")` works from a 5-line script
- [ ] Strategy test suite never imports a broker package
- [ ] One Instrument type; one Order type; one Position type (grep gate)
- [ ] OMS unit tests run with pure fakes (no EventBus/SQLite required for core lifecycle)
- [ ] Backtest and live share Instrument API
- [ ] New junior engineer places paper order via Instrument without reading gateway docs

---

## 10. Explicit Non-Goals (board)

- Microservices / Kafka-first redesign
- Rewriting Dhan/Upstox HTTP clients from scratch
- UI redesign
- New broker before Wave B completes
- “Clean architecture purity” that deletes working resilience without replacement

---

## 11. Recommendation to Product Validation Council

> Would an experienced trader trust this?

**Today:** Partially — paper path and domain objects are legible; live path still feels like an SDK wrapping broker APIs.  
**After Waves A–D:** Yes for research + paper + disciplined live, if OMS spine and Session DX land.

**Immediate next engineering action:** Execute **Wave A** (isolation truth) then **Wave B** (finish kernel move) on this branch. Do not start new features that deepen `brokers.common` residual ownership.

---

## Appendix A — Size snapshot (prod, excl tests)

| Package | Files | LOC |
|---------|-------|-----|
| brokers.dhan | 71 | 17.9k |
| analytics | 92 | 16.2k |
| cli | 90 | 14.0k |
| domain | 147 | 13.0k |
| brokers.upstox | 117 | 12.3k |
| datalake | 77 | 10.6k |
| brokers.common | 103 | 9.5k (mix of shims + residual) |
| infrastructure | 52 | 9.0k |
| application | 48 | 7.6k |
| api | 42 | 7.5k |
| tradex | 45 | 7.1k |

## Appendix B — Prior work recognized

Waves already landed on this branch (do not re-litigate): D1 registry, domain port hygiene, OMS port extraction slices, `tradex.runtime` kernel extraction, Instrument-centric domain object, architecture fitness tests, import-linter contracts.

This board report **supersedes** stale claims in `TECHNICAL_DEBT.md` that still list D1 as failing fitness.
