# Trading OS — Delivery Backlog

**Owner:** Product + Engineering  
**Living document** — reassess after every shipped iteration.  
**Last updated:** 2026-07-09 (post-W3: DV-013 greeks + sandbox smoke script)  
**Constitution:** [`docs/OPERATING_MODEL.md`](../docs/OPERATING_MODEL.md) — single source of truth for how we work.  
**Dependency graph:** [`DELIVERY_DEPENDENCY_GRAPH.md`](./DELIVERY_DEPENDENCY_GRAPH.md)

This is a **Delivery Backlog**, not a refactor backlog.  
Work is organized by **business capabilities (Epics)**. Engineering cleanup is classified A/B/C and only scheduled when it enables delivery, reliability, or maintainability of code we must touch.

---

## Mission (reminder)

> Build a Trading Operating System that delivers production-ready features continuously while improving the architecture through small, incremental, measurable changes.

---

## Classification

| Class | Meaning | Scheduling rule |
|-------|---------|-----------------|
| **A** | Production blocker (money, security, correctness, live path) | Fix immediately |
| **B** | Blocks feature delivery in a capability area | Fix when working that epic/slice |
| **C** | Engineering improvement | Boy Scout only inside touched modules — no standalone program |

## Status legend

| Status | Meaning |
|--------|---------|
| `todo` | Not started |
| `ready` | Plan approved; can start |
| `doing` | In progress |
| `done` | Definition of Done met + shipped |
| `deferred` | Explicitly deferred with justification |
| `blocked` | Waiting on dependency / decision |

---

## Active focus

| Priority | Item | Status |
|----------|------|--------|
| **Done W1** | Epic 1 + paper Trading + paper Derivatives + Analytics session smoke | **shipped** |
| **Done W2** | MA-024 · TR-022/024 · sandbox gate · DV-012 | **shipped** |
| **Done W3** | AU-010/011/012 · AN-011 | **shipped** |
| **Done post-W3** | DV-013 greeks paper · sandbox smoke script · dhan list_capabilities | **shipped** |
| **Next** | Refresh sandbox token for green place/cancel · Epic 6 only when needed | `todo` |

**No pure-refactor waves are active.** Broker shim cleanup and CLI splits are Category B/C only.

---

## Epic overview

| Epic | Capability | Outcome when done | Status |
|------|------------|-------------------|--------|
| **1** | Market Access | Connect → resolve instrument → quote → history → subscribe | **`done`** (incl. MA-024 wiring) |
| **2** | Trading | Orders, positions, portfolio on single OMS path; sim + live modes | **paper + trade gates + sandbox product path**; LIVE money still desk-gated |
| **3** | Derivatives | Option chain, strikes, basic Greeks path via product API | **paper chain + greeks done**; live chain gated |
| **4** | Analytics | Scanner / backtest / research on same session model | **AN-010 + AN-011 done** |
| **5** | Automation | Strategy loop, risk, kill switch | **AU-010/011/012 done** (paper product path) |
| **6** | AI | Assistive/automation features on stable 1–3 | **todo** |

Each epic ships **vertical slices**. Do not wait for an entire epic to release value.

---

# Epic 1 — Market Access

**Goal:** A user can open a session and obtain trustworthy market data through the public object model without importing gateways.

**Product path:**

```python
import tradex
session = tradex.connect("paper")                 # or dhan/upstox mode="market"
stock = session.universe.equity("RELIANCE")
stock.refresh()
series = stock.history(timeframe="1D", days=5)
handle = stock.subscribe()
session.close()
```

**Plan:** [`EPIC_01_MARKET_ACCESS_PLAN.md`](./EPIC_01_MARKET_ACCESS_PLAN.md) — **approved and delivered** (Epic 1 closed for delivery 2026-07-09).

| ID | Slice / item | Class | Status | Notes |
|----|--------------|-------|--------|-------|
| MA-001 | Epic 1 implementation plan | — | `done` | [`EPIC_01_MARKET_ACCESS_PLAN.md`](./EPIC_01_MARKET_ACCESS_PLAN.md) |
| MA-010 | Paper: instrument lookup + quote refresh E2E | B | `done` | `tests/e2e/test_market_access.py` |
| MA-011 | Paper: history facade returns consistent series | B | `done` | Fixed `PaperDataProvider.get_history` kwargs bug |
| MA-012 | Paper: subscribe / unsubscribe lifecycle | B | `done` | Initial snapshot + handle lifecycle |
| MA-020 | Live mode=`market`: connect without OMS | A/B | `done` | Unit + existing factory tests |
| MA-021 | Live: symbol → broker token resolution | B | `done` | Verified via live Dhan LTP/history path |
| MA-022 | Live: quote mapping Quote → QuoteSnapshot | B | `done` | Existing mapping sufficient for MA-S2 |
| MA-023 | Live: history for one liquid equity | B | `done` | `test_L_DHAN_MARKET_ACCESS_QUOTE_HISTORY` (gated) |
| MA-024 | Live: WS subscribe tick updates instrument | B | `done` | Fixed stream kwargs + QuoteSnapshot wrap; unit + gated smoke |
| MA-030 | Public SDK docs + quickstart for data-only | C | `done` | OBJECT_MODEL + quickstart |
| MA-031 | Contract tests: DataProvider conformance (paper) | B | `done` | `brokers/paper/tests/test_data_provider_history.py` |
| MA-090 | Secrets not in repo / env hygiene for live runs | A | `done` | `.env*` gitignored; not tracked; local only |

**Epic 1 exit (definition):** Paper path green in CI ✅; live Dhan quote+history gated ✅; live subscribe deferred (MA-024) ✅; no gateway imports in product examples ✅.

### MA-024 resolution (W2 — 2026-07-09)

**Fixed** in `brokers/dhan/data_provider.py` (+ deprecated `providers/dhan` mirror):

1. Call `gateway.stream(..., mode=QUOTE|DEPTH, on_tick=...)` (was wrong positional/kwargs).  
2. Normalize ticks → `QuoteSnapshot` before instrument callback.  
3. Unit tests: `brokers/dhan/tests/unit/test_data_provider_subscribe.py`.  
4. Gated live smoke: `test_L_MA024_SUBSCRIBE_HANDLE_WITHOUT_TICK_WAIT` (handle lifecycle; no tick wait).

---

# Epic 2 — Trading

**Goal:** Place, modify, cancel orders; see positions and portfolio; single OMS admission path.

**Foundation already delivered (do not re-open as refactor):**

| ID | Item | Class | Status |
|----|------|-------|--------|
| TR-001 | Harden live OMS standalone fallback | A | `done` (was ENG-001) |
| TR-002 | Fix Upstox modify_order contract | A | `done` (ENG-002) |
| TR-003 | Fix live signal sizing | A | `done` (ENG-003) |
| TR-004 | Secure API auth default | A | `done` (ENG-004) |
| TR-005 | Fail-closed unmapped order status | A | `done` (ENG-005) |
| TR-006 | Crash-replay positions after OMS reject | A | `done` (ENG-006) |
| TR-010 | EventLog recovery on primary path | A | `done` (ENG-010) |
| TR-011 | Single production composition root | A | `done` (ENG-011) |
| TR-012 | Research/live parity modes | B | `done` (ENG-012) |
| TR-013 | Port-level broker contracts (paper) | B | `done` (ENG-013) |
| TR-014 | Capital provider fail-closed | A | `done` (ENG-039) |

**Remaining delivery slices (start after Epic 1 shippable data path):**

| ID | Slice / item | Class | Status | Notes |
|----|--------------|-------|--------|-------|
| TR-020 | Sim: buy/sell/cancel via `Instrument` + session | B | `done` | `tests/e2e/test_trading_object_model.py` |
| TR-021 | Positions + portfolio read after fills (paper) | B | `done` | account.refresh → positions/funds |
| TR-022 | mode=`trade` requires process OMS | A | `done` | `tests/e2e/test_trading_w2.py` — OMS_REQUIRED / orders_enabled |
| TR-022s | **Sandbox** product-path place + cancel | A | `done` | `tests/e2e/test_sandbox_product_orders.py` (`-m sandbox`); env `.env.dhan.sandbox` |
| TR-023 | Idempotent submit / correlation_id behavior | A | `done` | same correlation_id → same order_id |
| TR-024 | Modify + cancel contracts | A/B | `done` | Paper OMS + sandbox path; LIVE production still desk-gated |
| TR-025 | Fix Dhan gateway `place_order` → BrokerOrderPayload | A | `done` | Was TypeError on adapter; blocks all Dhan writes |
| TR-030 | Event bus mark-after-success | A | `deferred` | Needs designed recovery model (was ENG-038) |
| TR-031 | Partial-fill paper book | C | `deferred` | After more parity use (DEF-04) |
| TR-032 | HA multi-writer order store | C | `deferred` | Needs multi-process product req (DEF-03) |

---

# Epic 3 — Derivatives

| ID | Slice / item | Class | Status | Notes |
|----|--------------|-------|--------|-------|
| DV-010 | `session.universe.index` + `option_chain()` paper | B | `done` | `tests/e2e/test_derivatives_object_model.py`; paper spot fix |
| DV-011 | Strike selection helpers (ATM/OTM) | B | `done` | select_strikes ATM/OTM |
| DV-012 | Live option chain one underlying | B | `done` | Gated L3: chain ATM + universe.index path |
| DV-013 | Basic Greeks path (product API) | B | `done` | paper synthetic greeks + `test_derivatives_greeks.py`; live soft L3 |
| DV-020 | Chain normalizer edge cases | C | `todo` | Boy Scout when touching options |

---

# Epic 4 — Analytics

| ID | Slice / item | Class | Status | Notes |
|----|--------------|-------|--------|-------|
| AN-010 | Scanner runs on session/universe instruments | B | `done` | Session→history→`analytics.scanner` smoke; dual scanners: use, don’t merge |
| AN-011 | Backtest uses same Instrument/history types | B | `done` | `tests/e2e/test_backtest_session_history.py` — pure_sim + PARITY gate |
| AN-012 | ResearchMode PURE_SIM / PARITY documented + tested | B | `done` foundation (ENG-012) |
| AN-020 | Dual scanners ownership docs | C | `done` (ENG-020) |

---

# Epic 5 — Automation

| ID | Slice / item | Class | Status | Notes |
|----|--------------|-------|--------|-------|
| AU-010 | Strategy run loop on product session | B | `done` | history → SMA signal → place; `test_automation_w3.py` |
| AU-011 | Kill switch + risk gates | A | `done` | paper OMS kill switch block/clear (live desk still separate) |
| AU-012 | Signal → OMS path regression | A | `done` | SignalDTO → Instrument.buy via session |

---

# Epic 6 — AI

| ID | Slice / item | Class | Status | Notes |
|----|--------------|-------|--------|-------|
| AI-010 | Define first AI capability only after Epics 1–3 stable | C | `deferred` | No speculative AI platform work |

---

# Cross-cutting engineering (no epic of their own)

These are **not** standalone programs. Pull into a feature when they block it.

| ID | Item | Class | Status | Pull when… |
|----|------|-------|--------|------------|
| XE-001 | `brokers.common` residual shims → `tradex.runtime` | C | continuous Boy Scout | Editing import paths anyway |
| XE-002 | Split CLI `BrokerService` | B/C | `deferred` | Next CLI feature needs a cut (ENG-019) |
| XE-003 | Split `capability_manifest.py` | C | `deferred` | Next capability edit (ENG-030) |
| XE-004 | Dual HTTP metric servers | B | `deferred` | Ops ownership (ENG-036) |
| XE-005 | `TradingContext` SRP split | B/C | `deferred` | Feature collides with god-context (ENG-037) |
| XE-006 | Import-linter / fitness honesty | A/B | `done` foundation (ENG-018) | Regressions only |
| XE-007 | Gateway surface freeze tests | B | `done` (brokers wave D) | Changing gateway API |
| XE-008 | Full rewrite Dhan/Upstox trees | C | **rejected** | Never as a program (DEF-01) |
| XE-009 | Decorator instrument stack | C | **rejected** | Board: capabilities preferred (DEF-02) |
| XE-010 | Premature WS p99 optimization | C | `deferred` | After SLO data (DEF-05) |

---

# Completed foundation (archive)

Historical engineering IDs mapped into delivery language. Kept for traceability — **not a work queue**.

| Legacy | Delivery ID | Notes |
|--------|-------------|-------|
| ENG-001–006 | TR-001–006 | P0 money/safety |
| ENG-010–013 | TR-010–013 | Spine, recovery, parity, contracts |
| ENG-014–018, 020 | XE / done | Shims guidance, dead code, providers, reconnect, fitness, scanners docs |
| ENG-031–035, 039–042, 052 | done | Naming, capital fail-closed, metrics, architecture docs |
| Brokers waves A–D | XE-001/007 | Complete; residual cleanup is Boy Scout only |

See git history and prior backlog revisions for completion logs.

---

## How to use this backlog

1. Read **`docs/OPERATING_MODEL.md`** before planning work.  
2. Pick the **highest epic that is not done**, then the **smallest slice** with user value.  
3. Classify new findings **A / B / C** immediately.  
4. Category A → fix or explicitly block release.  
5. Category B → attach to the epic slice that needs it.  
6. Category C → no ticket that pauses delivery; Boy Scout in touch set.  
7. After ship: mark `done`, reassess order of remaining slices.  
8. **Do not** create “Refactor brokers” / “Clean architecture” epics.

---

## Work item template

```text
ID:
Epic:
Title:
User value:
Class: A | B | C
Engineering improvements required: (only enablers)
Tests:
Docs:
Acceptance criteria:
Status:
```
