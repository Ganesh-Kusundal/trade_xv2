# TradeXV2 → Trading OS: Architecture Review & Refreshed Transformation Roadmap

> **Review date:** 2026-07-12 · **Reviewer:** Chief Architect (automated code-derived review)
> **Review target:** working tree at `HEAD = 6b9bc6a0` (branch `refactor/structural-cleanup`)
> **Companion docs:** `roadmap.md`, `target-layering.md`, `baseline.md`, `backlog.md`, `adr/`
>
> This document **reviews the current app against the approved transformation plan** and
> refreshes the roadmap so it reflects *verified* state rather than the (now stale) baseline.
> Every claim below was checked against the actual source tree — not against the prose docs.

---

## 0. Review Methodology & Headline Findings

### 0.1 How this review was produced
- Read the approved plan artifacts: `roadmap.md`, `target-layering.md`, `baseline.md`, `backlog.md`, `adr/*`.
- Verified each claim against the **actual source tree** (LOC counts, `grep` for gap evidence, CI config, entry-points, branch topology).
- Did **not** trust the baseline metrics — they were written 2026-07-12 and the tree has since moved 190 commits ahead of `main`.

### 0.2 Headline findings (read these first)

| # | Finding | Severity | Evidence |
|---|---|---|---|
| F1 | **The baseline/roadmap docs are stale.** They claim "~773 tests, 56 arch tests" but the tree actually has **7,472 tests / 261 arch-test defs / 58 arch files**. Planning from the docs alone would mis-scope every later phase. | ⚠️ | `find tests -name test_*.py \| wc -l` = 775 files; `grep -rh 'def test_' tests \| wc -l` = 7,472 |
| F2 | **ADR-010 and ADR-011 are claimed in commits but the ADR documents are MISSING.** 10+ commits say "per ADR-011" (file-size limit 400 soft / 650 hard) but `docs/architecture/adr/` contains only ADR-0001…0005. | 🔴 | `git log --oneline --all \| grep ADR-011` (10 hits); `ls docs/architecture/adr/` (no 0010/0011) |
| F3 | **ADR-011 LOC gate exists but is neutered by a 38-entry exemption list.** `tests/architecture/test_file_size_limit.py` enforces 400 soft / 650 hard and runs in CI (`@pytest.mark.architecture`), but 38 files are exempted — several far above 650 (`capability_manifest/catalog.py` 895, `domain/universe.py` 700, `candles/historical.py` 666, `analytics/precompute_features.py` 678, `brokers/services/core.py` 570, `upstox/auth/token_manager.py` 574). The "hard limit" is effectively advisory for those. | ⚠️ | `tests/architecture/test_file_size_limit.py` (SOFT=400, HARD=650, 38-entry EXEMPTIONS dict) |
| F4 | **G7 (reflection kill-switch) has REGRESSED**, not improved. Baseline cited 1 `getattr` reach-through; the tree now has **6** (trading_orchestrator, order_placer ×2, reconciliation_service ×2, oms/context, production_readiness). | 🔴 | `grep -rn "getattr.*risk_manager\|getattr(order_manager" src/application/` → 6 hits |
| F5 | **G5 (duplicated infra) got WORSE on MCP**: baseline said 2 MCP servers; the tree now has **3** (`brokers/mcp`, `interface/agent/mcp_server.py`, `datalake/mcp`). | ⚠️ | `find src -path '*mcp*' -name '*.py'` |
| F6 | **`main` is 61 commits behind `HEAD` and the tree has ~13 divergent branches** (`phase1-7`, `dev`, `dev_temp`, `agent/p0-smart-gateway-contract`, `refactor/brokers-consolidation`, `step7changes`, …). The phase-5/6/7 branches are **older lines off `main`** (51–62 commits, but 128–139 *behind* HEAD) — they are not the current state and must not be merged blindly. | 🔴 | `git branch -v`; `git rev-list --count main..HEAD` = 190 |
| F7 | **A new god-object was introduced:** `src/domain/capability_manifest/catalog.py` (905 LOC) — a capability catalog that did not exist in the baseline. Capability-driven design is good intent; an un-decomposed 905-LOC module is not. | ⚠️ | LOC count |
| F8 | **G1, G3, G4, G5(event bus/idempotency/strategy), G6, G8 are still OPEN** in the tree despite phases 0–4 being "complete". The dev-platform cleanups (G8) were never done: `pytest_runner*.py`, `run_*.sh`, `verify_decomposition.py` still sit at repo root. | ⚠️ | See §2 |

**Bottom line:** The *bones* are strong and Phases 0–4 delivered real value (typed domain, event bus, architecture tests, ADRs, 7,472 tests, plugin discovery, capability manifest). But the plan's **governance claims are overstated** (ADR-011 "enforced" is false; baseline metrics wrong) and **the core broker/exchange-agnosticism gaps (G1, G3) and the silent-failure gaps (G6, G7) remain open** — exactly the items the roadmap labelled 🔴 blockers. The system is *not yet* an institutional Trading OS, but it is **evolvable**, not a rewrite candidate.

---

## 1. Verified Current State (corrected baseline)

| Aspect | Baseline doc claimed | Verified reality |
|---|---|---|
| Total tests | ~773 | **7,472** (`def test_`) across 775 files |
| Architecture tests | 56 defs | **261 defs** across 58 files |
| CI workflows | 8 | 8 (unchanged): `ci`, `architecture-enforcement`, `web`, `production_gate`, `dhan-regression`, `mutation_nightly`, `load-test`, `broker_live_certify` |
| God classes | UpstoxBroker ~50-adapter facade; RiskManager 678; TradingContext 809 | **Decomposed** (ADR-011): RiskManager→454, TradingContext→677, UpstoxTokenManager 574→231, plus Analytics/OMS/histories coordinators split |
| Shadow `brokers/` | 🔴 orphan at repo root | **DELETED** (G2 DONE) |
| New >650-LOC `src/` files | (none cited) | **~20**, incl. `capability_manifest/catalog.py` 905, `replay/engine.py` 826, `instruments/instrument.py` 819, `universe.py` 808, `candles/historical.py` 789 |
| `main` branch | implied current | **61 commits behind HEAD**; HEAD is the real tip |
| Plugin entry-points | `tradex.brokers` | `tradex.brokers` only; `tradex.exchanges` **not yet registered** (G3 foundation only) |

**Package LOC (verified):** domain 22,553 · application 16,420 · brokers 42,207 · infrastructure 17,579 · interface 23,750 · datalake 9,474 · analytics 18,035 · config 2,618 · runtime 1,965 · tradex 1,108. Total `src/` ≈ **175,780 LOC**.

---

## 2. Gap Status — Verified vs `backlog.md`

| Gap | backlog status | **Verified status** | Evidence (tree) |
|---|---|---|---|
| **G1** runtime couples to concrete brokers + `_active_name` string branch | TODO | **OPEN** — `_active_name == "dhan"` still at `trading_runtime_factory.py:105`; concrete `brokers.dhan.*/upstox.*/paper.*` imports centralized in `broker_accessors.py` (improvement: single import site, but still string-keyed, not enum/registry) | `grep _active_name src/runtime/` → 1 hit; `broker_accessors.py` imports `brokers.dhan.*`, `brokers.upstox.*` |
| **G2** shadow `brokers/dhan/*` | DONE | **DONE (verified)** — root `brokers/` gone; guard test `tests/architecture/test_no_shadow_broker_modules.py` | `ls brokers/` → none |
| **G3** datalake bakes in NSE/IST | TODO | **OPEN** — ports `ExchangeAdapter`/`TradingCalendar`/`ExchangeNotConfigured` now **exist** in `domain/ports`, but NSE literals remain in `datalake/ingestion/loader.py:36` (`NSE_MARKET_OPEN`), `datalake/research/api.py:63,111` (`exchange="NSE"`). No NSE *plugin* extracted. | `grep -rn 'exchange="NSE"\|NSE_MARKET_OPEN' src/datalake/` |
| **G4** two config systems | TODO | **OPEN** — `src/infrastructure/config/settings.py` (`SettingsLoaderBase`) still present alongside `src/config/schema.py` (`AppConfig`, 12 usages). ADR-003 approved but not implemented. | `ls src/infrastructure/config/`; `grep -rln AppConfig src/ \| wc -l` = 12 |
| **G5** duplicated infra (dual event bus, triple idempotency, 2 MCP, 2 strategy spines) | TODO | **OPEN + partially worse** — `event_bus/` still has `event_bus.py` + `async_event_bus.py` + `domain_bus_adapter.py` + `processed_trade_repository.py`; **3** MCP servers now (`brokers/mcp`, `interface/agent`, `datalake/mcp`); `LiveStrategyEngine` and `TradingOrchestrator` both still exist. | `ls src/infrastructure/event_bus/`; `find src -path '*mcp*'`; two strategy classes present |
| **G6** reconciliation off hot path | TODO | **OPEN** — reconciliation moved *into* brokers (`brokers/dhan/portfolio/reconciliation.py`, `brokers/upstox/reconciliation/service.py`, `brokers/common/recon_local.py`) but is **not on the OMS order-update hot path**; no `POSITION_DRIFT` event emitted. | `grep POSITION_DRIFT src/` → none |
| **G7** `getattr` kill-switch | TODO | **OPEN + REGRESSED** — 6 `getattr` reach-throughs to `_order_manager`/`risk_manager` (vs 1 in baseline). | `grep -rn getattr src/application/` → 6 |
| **G8** ad-hoc scripts at root | TODO | **OPEN** — `pytest_runner.py`, `pytest_runner2.py`, `pytest_runner3.py`, `run_all.sh`, `run_arch_tests.sh`, `run_replay_tests.py`, `run_tests.py`, `verify_decomposition.py` all still present. Phase-4 "complete" did **not** include this cleanup. | `ls *.py *.sh` at repo root |

**Net:** 1 of 8 gaps closed (G2). The 3 🔴 blockers from the original plan — G1 (runtime coupling), G3 (exchange-agnostic), and the silent-failure cluster (G6/G7) — are **all still open**.

---

## 3. Governance Red Flags (must fix before more refactoring)

These are process failures that make the *plan itself* untrustworthy. They are cheap to fix and are prerequisites for Phase 5.

| ID | Issue | Fix |
|---|---|---|
| GOV-1 | ADR-010 / ADR-011 referenced in 10+ commits but **no ADR document exists** | Write `adr/0010-split-events-types.md` and `adr/0011-file-size-limit.md` from the commits' intent; back-link commits |
| GOV-2 | ADR-011 LOC gate **exists** (`tests/architecture/test_file_size_limit.py`, runs in CI) but is **neutered by a 38-entry exemption list**; several exempted files sit far above 650 (catalog.py 895, universe.py 700, candles/historical.py 666). The "hard limit" is advisory for those 38. | Keep the gate; **drive the exemption list to zero** by decomposing each listed file (P5-10); every new exemption requires an owner + due-date. Also write the missing ADR-0011 doc (GOV-1) |
| GOV-3 | `main` 61 commits behind `HEAD`; ~13 divergent branches | Pick `refactor/structural-cleanup` as the integration trunk, fast-forward `main`, prune/merge the `phase1-7` + `dev*` + `agent/*` branches (they are behind HEAD and risk being merged by mistake) |
| GOV-4 | `baseline.md` metrics wrong | Re-baseline test count / arch-test count / LOC in `baseline.md` §6 and `backlog.md` "Backlog Health" |
| GOV-5 | New 905-LOC `capability_manifest/catalog.py` is **exempted** (not uncovered) in the LOC gate | Fold into P5-10 decomposition; remove its exemption once ≤650 |

---

## 4. Refreshed Transformation Roadmap

Phases 0–4 are treated as **delivered** (with the corrections above). The remaining program is **Phase 5 (core gaps) → Phase 6 (capabilities) → Phase 7 (hardening)**, preceded by a mandatory **Governance Gate**. The dependency graph and continuous-improvement loop from `roadmap.md` are retained.

### 4.0 Governance Gate (precedes Phase 5) — NEW

**Objective.** Make the plan and the trunk trustworthy before any further behavior change.
**Why.** F2/F3/F6 show the current plan claims things the tree does not honor (ADR-011 "enforced", `main` current, baseline metrics). Refactoring on top of an untrustworthy plan risks repeating the god-class churn.
**Scope.** Docs, CI, branch topology. **No business logic.**
**Deliverables.** ADR-0010/0011 docs; enforced LOC gate; `main` fast-forward + branch prune; re-baselined metrics.
**Tasks.**
| ID | Description | Dep | Output | Complexity | Risk | Acceptance |
|---|---|---|---|---|---|---|
| GG-1 | Write ADR-0010 (events/types split) + ADR-0011 (file-size limit) | — | ADR docs | S | none | docs merged, link commits |
| GG-2 | LOC gate already exists (`tests/architecture/test_file_size_limit.py`, CI-enforced) but has a 38-entry exemption list. **Drive the list to zero**: decompose each exempted file (P5-10); forbid new exemptions without owner+due-date; add a pre-commit guard so new files can't exceed 400 | GG-1 | gate | M | churn | exemption list shrinks each milestone; new files blocked at ≤400 |
| GG-3 | Fast-forward `main` to HEAD; delete/merge divergent `phase1-7`/`dev*` branches | — | clean trunk | S | lost WIP | `main` == HEAD; ≤3 long-lived branches |
| GG-4 | Re-baseline `baseline.md` §6 + `backlog.md` health metrics | GG-3 | docs | S | n/a | numbers match tree |
**Risks.** GG-2 flag-day on 20 oversized files → ship with an *exceptions* list that each has an owner + Phase-5 task to close.
**Exit.** ADR-0010/0011 exist; LOC gate red on new violations; `main`==HEAD; metrics re-baselined.

---

### Phase 5 — Core Platform Refactoring (the real remaining work)

**Objective.** Close G1, G3, G4, G5, G6, G7, G8 with the smallest safe diffs. Each task independently releasable.
**Why.** These are the only blockers to broker/exchange-agnosticism and to silent-failure safety.
**Scope.** `runtime/`, `datalake/`, `infrastructure/`, `application/`, repo root.
**Deliverables.** Clean layers; plugin registry (broker **and** exchange); single config/bus/idempotency; reconciliation on hot path; `RiskGate` port; consolidated dev platform; deleted ad-hoc scripts.

| ID | Description | Dep | Sev | Complexity | Risk | Acceptance |
|---|---|---|---|---|---|---|
| P5-1 | **G1** — replace `_active_name` string branch + concrete imports with enum-keyed `BrokerRegistry`; keep `runtime/` the only concrete-import site (it already is, via `broker_accessors.py` — promote to registry) | GG-2 | 🔴 | M | regress | no `_active_name`; import-linter proves no direct broker import outside `runtime/`; broker selected by `broker_id` enum |
| P5-2 | **G3** — extract NSE calendar/conventions into `plugins/exchanges/nse` (new `tradex.exchanges` entry-point); `datalake` reads conventions only via active `ExchangeAdapter`; raise `ExchangeNotConfigured` when none registered | P5-1, ADR-005 | 🔴 | L | behavior change | zero `exchange="NSE"`/`NSE_MARKET_OPEN` literals in `src/datalake`; unregistered exchange raises |
| P5-3 | **G4** — deprecate `infrastructure/config/settings.py`; route all config through `AppConfig`; delete `SettingsLoaderBase` | ADR-003 | ⚠️ | M | drift during cutover | `grep SettingsLoaderBase src/` → 0 |
| P5-4 | **G5 (event bus)** — merge `event_bus.py` + `async_event_bus.py` + `domain_bus_adapter.py` into one core + thin async wrapper; one `IdempotencyService` (absorb `ProcessedTradeRepository`) | ADR-004 | ⚠️ | M | regress | one bus core; `ProcessedTradeRepository` gone |
| P5-5 | **G5 (MCP)** — consolidate 3 MCP servers behind one facade reusing one guardrail/validation path; tool schemas stable contract | P5-4 | ⚠️ | M | agent breakage | 1 MCP server; `brokers.mcp`/`datalake.mcp` import the facade |
| P5-6 | **G5 (strategy spine)** — pick one execution spine (`TradingOrchestrator` *or* `LiveStrategyEngine`); the other delegates; shared `evaluate→place` path | P2 | ⚠️ | M | break | single spine; arch test forbids duplicate |
| P5-7 | **G6** — wire `ReconciliationEngine` into order-update hot path; emit `POSITION_DRIFT`; auto-heal from broker-authoritative state | P5-1 | ⚠️ | M | false heal | drift heals automatically; `POSITION_DRIFT` emitted |
| P5-8 | **G7** — replace all 6 `getattr` reach-throughs with injected `RiskGate` / explicit accessors | P5-1 | ⚠️ | S | behavior | zero `getattr(..., "risk_manager")`; kill-switch via port |
| P5-9 | **G8** — delete `pytest_runner*.py`/`run_*.sh`/`verify_decomposition.py`;等价 via `tradex` CLI/MCP | P4 | ⚠️ | S | script loss | scripts gone; `tradex` covers them |
| P5-10 | **GOV** — decompose new god objects (`capability_manifest/catalog.py` 905, `replay/engine.py` 826, `instruments/instrument.py` 819) under the now-enforced LOC gate | GG-2 | ⚠️ | M | churn | all ≤650 LOC (or on exception list with owner) |

**Risks.** (a) Shadow-file regression — guarded by G2's import-resolution test. (b) Config drift during cutover — P5-3 ships behind a deprecation shim. (c) MCP agent breakage — keep schemas stable across P5-5.
**Exit.** import-linter proves: no broker string branching outside `runtime/`; no direct broker import outside `runtime/`; datalake zero NSE/IST literals; one event bus; one idempotency; zero `getattr` kill-switch; arch tests + CI green; `main`==HEAD.

---

### Phase 6 — Feature Delivery (each independently releasable)

**Objective.** Ship complete capabilities on the now-clean foundation.
**Capabilities.** Market Access · Trading · Options · Portfolio · Analytics · Replay · Strategy Engine · AI Agents.
**Per capability contract (from `roadmap.md` P6):** define → implement → integration test (real broker sandbox + golden datasets) → parity test (backtest & live share execution logic; zero-parity rule enforced by an arch test) → release behind flag.
**Tasks.** `P6-<cap>-1..5` per capability. **New governance task:** `P6-0` — every capability must have a stable `tradex` SDK + `tradex` CLI + MCP surface (closes the "no ad-hoc scripts" principle for features too).
**Risks.** Parity drift → shared execution path enforced by an architecture test (ties to P5-6).
**Exit.** Each capability releasable + tested + parity-verified behind a flag.

---

### Phase 7 — Production Hardening

**Objective.** Operational excellence for real money.
**Deliverables.** Perf/load suites (extend `load-test.yml`, `production_gate.yml`); chaos/recovery drills; metrics/tracing/alerting; security review (bandit/supply-chain already configured); runbooks; continuous-improvement loop.
**Tasks.** `P7-1` load/perf · `P7-2` chaos+recovery · `P7-3` observability · `P7-4` security · `P7-5` runbooks.
**Risks.** Untested recovery → chaos drills mandatory before go-live (ties to G6 hot-path reconciliation).
**Exit.** Production validation complete; runbooks published; improvement loop running.

---

## 5. Continuous Improvement Loop (from Phase 1, now enforced)

Review current implementation → validate assumptions → design smallest safe improvement → implement incrementally → remove duplication where it helps → improve tests → verify via SDK/CLI/MCP → update docs → **enforce architecture rules (now real, GOV-2)** → keep app deployable → reassess backlog → next iteration.

---

## 6. Updated Risk Register

| Risk | Sev | Phase | Mitigation |
|---|---|---|---|
| Plan claims unenforced rules (ADR-011 "hard limit") | 🔴 | GG-2 | write ADR + enforce in CI/pre-commit |
| `main` stale; ~13 divergent branches | 🔴 | GG-3 | fast-forward + prune; single trunk |
| `runtime/` concrete-broker coupling + string branch | 🔴 | P5-1 | enum registry; `runtime`-only imports |
| NSE/IST hardcodes block exchange-agnostic | 🔴 | P5-2 | `ExchangeAdapter`/`TradingCalendar` plugin |
| Reconciliation off hot path → silent drift | ⚠️ | P5-7 | wire into update path; `POSITION_DRIFT` |
| Reflection kill-switch fragility (REGRESSED 1→6) | ⚠️ | P5-8 | `RiskGate` port |
| Duplicated infra (bus/idempotency/MCP/strategy) | ⚠️ | P5-4/5/6 | collapse each |
| Config drift (two systems) | ⚠️ | P5-3 | single source |
| Ad-hoc scripts / no dev platform | ⚠️ | P5-9 | developer platform |
| New god objects (`catalog.py` 905, etc.) | ⚠️ | P5-10 | LOC gate + decompose |

---

## 7. Success Criteria (refreshed)

- Every milestone delivers measurable value; system stays deployable + CI-green after each phase.
- **Plan honors reality:** ADR docs exist for every claimed rule; LOC/dependency gates are actually enforced; `main` is the deployable tip.
- Parallel ownership possible via frozen contracts + ownership matrix.
- Evolution, not rewrite (domain/application largely preserved).
- Each phase has inputs/outputs/deps/risks/acceptance/exit criteria.
- Roadmap executable by a senior engineer or AI agent with minimal ambiguity.

## 8. Next Action (do this first)

1. **Governance Gate (GG-1…GG-4)** — without it the rest of the plan is built on unverified claims. Specifically: write ADR-0010/0011, enforce the LOC gate, fast-forward `main` and prune the divergent `phase1-7`/`dev*` branches, re-baseline the metrics.
2. Then start **P5-1 (G1)** — it is the smallest 🔴 that unblocks broker-agnosticism and is a superset of the already-centralized `broker_accessors.py`.
3. G2 is done — no action.

> Note: the pre-existing `docs/architecture/roadmap.md` and `docs/TRANSFORMATION_ROADMAP.md` remain the canonical phase *structure*; this review **corrects their status claims** and adds the Governance Gate. Reconcile `backlog.md` statuses with §2 before starting P5.
