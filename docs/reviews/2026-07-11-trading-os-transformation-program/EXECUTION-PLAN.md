# Phase-by-Phase Execution Plan

Each phase lists: **Objective · Scope · Deliverables · Tasks · Acceptance · Risks · Exit criteria**.

Task IDs reference [ENGINEERING-BACKLOG.md](./ENGINEERING-BACKLOG.md).

---

## Phase 0 — Discovery & Baseline

### Objective

Establish an evidence-backed understanding of the working tree. Prevent architecture decisions based on documentation claims, stale CI, or assumptions about live behavior.

**Problems solved:** Unknown ownership, hidden silent failures, untrustworthy green CI, duplicate composition paths.

### Scope

- Entire repository: `src/`, `tests/`, `scripts/`, `.github/`, `docs/`
- All entry points: SDK, CLI, API, MCP, CI, scripts
- Excludes: credential values, live broker calls without env

### Deliverables

| Artifact | Location | Status |
|----------|----------|--------|
| Current-state architecture audit | `docs/reviews/2026-07-11-trading-os-architecture-audit/` | ✅ Complete |
| Repository / package map | `01-repository-inventory.md` | ✅ |
| Runtime flow traces | `02-runtime-flows.md` | ✅ |
| Validation audit | `04-validation-audit.md` | ✅ |
| Ranked findings + contract | `05-findings-and-contract.md` | ✅ |
| Target architecture (evolutionary) | `06-target-architecture.md` | ✅ |
| Prioritized backlog | `07-backlog.md` (AUDIT-*) | ✅ |
| Evidence appendix | `09-evidence-appendix.md` | ✅ |
| Executive canvas | `CANVAS.md` | ✅ |

### Tasks (completed)

| Task ID | Description | Output |
|---------|-------------|--------|
| TRANS-P0-001 | Full file census by package | Inventory doc |
| TRANS-P0-002 | Graphify + import-linter execution | 3 broken contracts identified |
| TRANS-P0-003 | CI path drift verification | 15+ stale paths catalogued |
| TRANS-P0-004 | E2E flow reconstruction (static) | Flow traces with line evidence |
| TRANS-P0-005 | Technical debt + risk register seed | Findings A/B/C |

### Acceptance criteria

- [x] Every material claim cites file/symbol/test/workflow
- [x] Live checks classified: passed / failed / not_run / blocked_by_environment
- [x] Safety baseline documented (no fabricated broker success)
- [x] Transformation program authorized to proceed

### Risks

| Risk | Mitigation |
|------|------------|
| Audit stale within weeks | Re-run inventory on major refactors; `test_workflow_paths` in P3 |
| Graphify drift | `graphify update .` after code changes affecting graph |

### Exit criteria → Phase 1

- [x] Audit pack published
- [x] Chief Architect sign-off on verdict: **not production for unattended live capital**
- [x] ENGINEERING-BACKLOG absorbed from AUDIT-*

---

## Phase 1 — Architecture Foundation

### Objective

Define the **target Trading OS architecture** as enforceable contracts — not aspirational diagrams. Enable parallel teams and AI agents to make consistent decisions without central review for every PR.

**Problems solved:** Fragmented mental models, broker leakage into domain, unclear ownership, speculative refactors.

### Scope

- Architecture handbook (vision, principles, bounded contexts)
- Ubiquitous language glossary
- Package structure and dependency rules (extends import-linter)
- Event model and object model specifications
- Extension/plugin model
- Public SDK surface contract
- ADRs for boundary changes in this phase

**Out of scope:** Production code moves (except ADR-accompanying architecture tests that fail on violations — can stub).

### Deliverables

| Artifact | Path | Owner |
|----------|------|-------|
| Architecture Handbook v1 | `docs/architecture/HANDBOOK.md` | Domain & Contracts |
| Ubiquitous Language Glossary | `docs/architecture/GLOSSARY.md` | Domain & Contracts |
| Bounded Context Map (diagram) | `ARCHITECTURE-ARTIFACTS.md` | Chief Architect |
| Dependency Rules Matrix | `docs/architecture/DEPENDENCY_RULES.md` | Runtime/Platform |
| Event Catalog v1 | `docs/architecture/EVENT_CATALOG.md` | Domain & Contracts |
| Object Model Spec | `docs/architecture/OBJECT_MODEL.md` | Domain & Contracts |
| Plugin Contract Spec | `docs/architecture/PLUGIN_CONTRACT.md` | Broker Platform |
| Public SDK Contract | `docs/architecture/SDK_CONTRACT.md` | Runtime/Platform |
| ADR-015 Execution Ledger Authority | `docs/architecture/adrs/adr-015-execution-ledger.md` | OMS/Execution |
| ADR-016 Market Data Event Bus | `docs/architecture/adrs/adr-016-market-data-bus.md` | Market Data |
| ADR-017 Single Composition Root | `docs/architecture/adrs/adr-017-composition-root.md` | Runtime/Platform |
| ADR-018 Certification Truth Tiers | `docs/architecture/adrs/adr-018-certification-tiers.md` | Integration/Release |
| Architecture guardrails test plan | `TESTING-STRATEGY.md` § architecture | Integration/Release |

### Tasks

| Task ID | Description | Deps | Complexity | Output |
|---------|-------------|------|------------|--------|
| TRANS-P1-001 | Write Architecture Handbook (vision, principles, context map) | P0 | M | `HANDBOOK.md` |
| TRANS-P1-002 | Ubiquitous language glossary (50+ terms) | P0 | S | `GLOSSARY.md` |
| TRANS-P1-003 | Finalize bounded context ownership table | P0, design doc | S | Handbook §3 |
| TRANS-P1-004 | Event catalog: commands + domain events + integration DTOs | P1-003 | M | `EVENT_CATALOG.md` |
| TRANS-P1-005 | Object model: aggregates, invariants, legal transitions | P1-004 | M | `OBJECT_MODEL.md` |
| TRANS-P1-006 | Package structure target + shim removal conditions | P1-003 | M | Handbook §5 |
| TRANS-P1-007 | Dependency rules (allowed/forbidden matrix) | P1-006 | S | `DEPENDENCY_RULES.md` |
| TRANS-P1-008 | Plugin contract (entry points, registration, certification) | ADR-014 | M | `PLUGIN_CONTRACT.md` |
| TRANS-P1-009 | Public SDK contract (`tradex.connect`, session modes) | RUNTIME_KERNEL | S | `SDK_CONTRACT.md` |
| TRANS-P1-010 | Draft ADR-015 through ADR-018 | P1-004–009 | M | 4 ADR files |
| TRANS-P1-011 | Mermaid: context map, package, dependency | P1-006 | S | `ARCHITECTURE-ARTIFACTS.md` |
| TRANS-P1-012 | Architecture review gate (human + agent checklist) | P1-001 | S | Handbook §9 |

### Acceptance criteria

- [ ] Architecture Handbook approved by program owner
- [ ] All diagrams in `ARCHITECTURE-ARTIFACTS.md` complete
- [ ] Domain model validated against existing `src/domain/` (gap list documented)
- [ ] Event catalog covers order, fill, market data, reconciliation, lifecycle
- [ ] ADR-015–018 in `Accepted` or `Proposed` with no open blockers
- [ ] No contradiction with import-linter contracts in `pyproject.toml`
- [ ] AI agent checklist: any PR can be classified to one bounded context

### Risks

| Risk | Mitigation |
|------|------------|
| Handbook becomes shelfware | Every P5 task must cite handbook section |
| Over-specification | YAGNI rule in handbook; defer CQRS expansion beyond current dispatchers |
| Conflict with in-flight refactor branch | Handbook describes target; current gaps in "as-is" appendix |

### Exit criteria → Phase 2

- [ ] Handbook v1 merged to `main`
- [ ] ADR-015–018 accepted
- [ ] Phase 2 team has flow ownership assignments ([TEAM-OWNERSHIP.md](./TEAM-OWNERSHIP.md))
- [ ] Phase 3 CI truth **in progress** (not blocking Phase 2 docs)

---

## Phase 2 — Runtime & Flow Design

### Objective

Specify **how the Trading OS behaves** at runtime — every critical flow, state machine, failure mode, and recovery path. Flow specs become contract tests in Phase 3 and implementation guides in Phase 5.

**Problems solved:** "Should work" assumptions, silent failures, asymmetric broker paths, unclear UNKNOWN recovery.

### Scope

- Startup, shutdown, recovery
- Broker connection + authentication + token refresh
- Instrument lifecycle + security mapping
- Historical data, quote, subscription flows
- Order, position, portfolio, reconciliation lifecycles
- Replay/backtest/paper/live mode routing
- Error handling taxonomy

**Out of scope:** Implementing fixes (Phase 5); CI repair (Phase 3).

### Deliverables

| Artifact | Path |
|----------|------|
| Runtime Flow Catalog | `docs/architecture/FLOWS.md` |
| State machine specs | `docs/architecture/STATE_MACHINES.md` |
| Sequence diagrams (10+) | `ARCHITECTURE-ARTIFACTS.md` § flows |
| Error handling taxonomy | `docs/architecture/ERROR_TAXONOMY.md` |
| Expected Behavior Contract (executable checklist) | extends audit `05-findings-and-contract.md` |
| Flow contract test stubs | `tests/architecture/test_flow_contracts.py` |

### Tasks

| Task ID | Description | Deps | Complexity |
|---------|-------------|------|------------|
| TRANS-P2-001 | Startup flow (all entry points → readiness) | P1, audit flows | M |
| TRANS-P2-002 | Shutdown + kill-switch flow | P2-001 | S |
| TRANS-P2-003 | Recovery flow (restart, UNKNOWN, recon) | P2-001, ADR-015 | M |
| TRANS-P2-004 | Broker auth + token refresh (Dhan, Upstox) | audit §2 | M |
| TRANS-P2-005 | Instrument lifecycle + security mapping | P1 object model | M |
| TRANS-P2-006 | Historical data flow | datalake + providers | S |
| TRANS-P2-007 | Quote + subscription flow (canonical bus path) | ADR-016 | M |
| TRANS-P2-008 | Order lifecycle state machine | P1-005, audit §3 | M |
| TRANS-P2-009 | Fill ingress + position projection flow | ADR-015 | M |
| TRANS-P2-010 | Portfolio + PnL flow | P2-009 | S |
| TRANS-P2-011 | Reconciliation + drift repair flow | audit A-05 | M |
| TRANS-P2-012 | Replay flow (determinism) | CQRS doc | S |
| TRANS-P2-013 | Mode routing (live/paper/replay/backtest) | audit §4 | M |
| TRANS-P2-014 | Error taxonomy (loud vs silent, fail-closed rules) | audit contract | M |
| TRANS-P2-015 | `test_flow_contracts.py` stubs (xfail → pass in P5) | P2-001–014 | M |

### Acceptance criteria

- [ ] Every flow in FLOWS.md has: entry point, owner, inputs, outputs, failure semantics
- [ ] State machines cover: Order, Position, Subscription, BrokerSession
- [ ] Sequence diagrams for: PlaceOrder, FillIngress, Reconcile, Subscribe, Startup
- [ ] Upstox vs Dhan bus asymmetry documented as **gap** with target in ADR-016
- [ ] UNKNOWN never transitions to success without reconciliation (explicit)
- [ ] `test_flow_contracts.py` exists; failures documented as expected until P5

### Risks

| Risk | Mitigation |
|------|------------|
| Flow spec diverges from code before P5 | Link each flow to file:line; CI checks file exists |
| Too many flows | P0 scope only; defer options-specific flows to P6 |

### Exit criteria → Phase 3 (parallel) / Phase 4 / Phase 5

- [ ] FLOWS.md + STATE_MACHINES.md merged
- [ ] Error taxonomy agreed with Integration/Release (CI gate semantics)
- [ ] Phase 3 CI truth **complete** before Phase 5 starts
- [ ] Flow contract tests committed (xfail allowed)

---

## Phase 3 — Engineering Standards

### Objective

Make **CI green mean real**. Establish enforceable engineering rules so architecture does not regress during Phase 5 refactoring.

**Problems solved:** 15+ broken CI paths, warn-only safety gates, 3 failing import-linter contracts, stale pre-commit.

### Scope

- CI workflow repair + workflow-reference architecture test
- Import-linter violation fixes (or ADR-approved ignores with expiry)
- Pre-commit alignment
- Testing standards document
- Architecture test expansion
- CI quality gate policy (blocking vs advisory)

### Deliverables

| Artifact | Path |
|----------|------|
| Repaired `.github/workflows/*.yml` | repo root |
| `tests/architecture/test_workflow_paths.py` | tests |
| `docs/engineering/STANDARDS.md` | docs |
| `docs/engineering/TESTING.md` | links to TESTING-STRATEGY |
| ADR-019 CI Gate Semantics | `adrs/adr-019-ci-gates.md` |
| Fixed `parity_gate.py`, `production_certification.py` | src, scripts |

### Tasks

| Task ID | Description | Deps | Complexity | Maps |
|---------|-------------|------|------------|------|
| TRANS-P3-001 | Repair all CI script/test paths | P0 | M | AUDIT-001 |
| TRANS-P3-002 | Fix replay verifier path + module import | P0 | S | AUDIT-002 |
| TRANS-P3-003 | Add `test_workflow_paths.py` | P3-001 | S | AUDIT-001 |
| TRANS-P3-004 | Remove `continue-on-error` on safety steps; ADR-019 | P3-001 | S | AUDIT-006 |
| TRANS-P3-005 | Fix pre-commit paths (`src/brokers/`, tests/) | P3-001 | S | AUDIT-001 |
| TRANS-P3-006 | Fix `production_certification.py` paths | P3-001 | M | AUDIT-001 |
| TRANS-P3-007 | Restore Dhan regression workflow paths | P3-001 | M | AUDIT-012 |
| TRANS-P3-008 | Prune stale `ignore_imports`; fix 3 broken contracts | P1-007 | L | AUDIT-004, AUDIT-007 |
| TRANS-P3-009 | Publish `STANDARDS.md` (naming, logging, errors) | P1 | M | — |
| TRANS-P3-010 | Architecture test: no domain broker imports | P3-008 | S | AUDIT-004 |
| TRANS-P3-011 | Architecture test: application no infra imports | P3-008 | S | AUDIT-007 |
| TRANS-P3-012 | Gate result semantics in all workflows | P3-004 | S | ADR-018 |

### Acceptance criteria

- [ ] `ci.yml` lint job passes on clean checkout
- [ ] `lint-imports`: 15/15 contracts pass
- [ ] `test_workflow_paths.py` passes; fails on intentional drift
- [ ] `parity_gate` replay check passes without `SKIP_PARITY_GATE`
- [ ] No `continue-on-error` on safety without `advisory:` label in workflow name
- [ ] `STANDARDS.md` published
- [ ] Collection errors < 3 (document remainder)

### Risks

| Risk | Mitigation |
|------|------------|
| Fixing CI exposes hundreds of test failures | Separate PR: paths first, then test fixes |
| Import-linter fixes require code changes | Tracing port + segment registry in P3-008 |

### Exit criteria → Phase 4 & Phase 5

- [ ] Full CI pipeline green on `main` (unit+component+arch minimum)
- [ ] Import-linter green
- [ ] ADR-019 accepted
- [ ] **Mandatory before any Phase 5 production refactor merge**

---

## Phase 4 — Developer Platform

### Objective

**No ad-hoc scripts** for validation. SDK, CLI, and MCP expose the same runtime contracts with explicit result states (`passed|failed|blocked`).

**Problems solved:** Fragmented doctor/verify paths, script drift, AI agents inventing checks.

### Scope

- Unified command surface: `doctor`, `verify`, `certify`, `benchmark`, `diagnose`, `replay`
- MCP tool parity with CLI
- Health/readiness endpoints
- Broker certification matrix expansion
- Golden datasets + sample apps
- Interactive notebook templates (optional)

### Deliverables

| Artifact | Path |
|----------|------|
| Developer Platform Spec | [DEVELOPER-PLATFORM.md](./DEVELOPER-PLATFORM.md) |
| `broker doctor` unified matrix | `src/brokers/diagnostics/` |
| Certification JSON schema v2 | `src/brokers/certification/` |
| API `/health` + `/ready` contract | `src/interface/api/` |
| Golden dataset manifest | `tests/fixtures/golden/` |
| Sample app: minimal live-readonly | `examples/minimal_session/` |

### Tasks

| Task ID | Description | Deps | Complexity |
|---------|-------------|------|------------|
| TRANS-P4-001 | Developer platform spec (commands, result states) | P1, P2 | M |
| TRANS-P4-002 | Unify `doctor` across SDK/CLI/MCP | P3 | L |
| TRANS-P4-003 | Unify `verify` + certification JSON schema | P3, ADR-018 | M |
| TRANS-P4-004 | `certify` tiers: offline, paper, live-readonly, sandbox | P3 | M |
| TRANS-P4-005 | API readiness: bus, ledger, broker session, recon | P2-001 | M |
| TRANS-P4-006 | MCP tools mirror CLI verify/certify | P4-002 | M |
| TRANS-P4-007 | Golden datasets (recorded ticks, orders — no synthetic) | P2 | M |
| TRANS-P4-008 | Sample app + notebook template | P4-001 | S |
| TRANS-P4-009 | Deprecation list for ad-hoc scripts | P4-001 | S |
| TRANS-P4-010 | Architecture test: CLI/MCP/SDK same cert module | P4-003 | S |

### Acceptance criteria

- [ ] `broker --broker paper doctor` returns structured JSON with per-check status
- [ ] `broker verify` and MCP tool invoke same `BrokerCertifier` code path
- [ ] API `/ready` returns 503 when reconciliation not ready (matches placement gate)
- [ ] Golden datasets run in CI without credentials
- [ ] `DEVELOPER-PLATFORM.md` complete
- [ ] Script deprecation plan has dates

### Risks

| Risk | Mitigation |
|------|------------|
| Live certify blocked by secrets | Tier 2 marked `blocked`; paper tier blocking in CI |
| MCP SDK drift | P4-010 architecture test |

### Exit criteria → Phase 5

- [ ] Paper certification blocking in CI
- [ ] Doctor/verify documented in Handbook
- [ ] Golden datasets in repo

---

## Phase 5 — Core Platform Refactoring

### Objective

Transform foundational modules **incrementally** behind feature flags and shadow mode. Establish single execution spine, canonical market-data bus, plugin registries.

**Problems solved:** Fragmented composition roots, dual order books, Upstox bus gap, shallow reconciliation, domain broker imports.

### Scope (priority order)

1. Brokers (segment registry, Upstox bus, dynamic factory)
2. Market Data (subscription SM, fail-closed drops)
3. OMS / Execution (tracing port, ledger authority, single composition root)
4. Portfolio (projection from ledger)
5. Reconciliation (unified compare, economics)
6. Analytics (mode parity only — no OMS imports)

**Out of scope:** New product features (Phase 6).

### Deliverables

| Deliverable | Description |
|-------------|-------------|
| `SegmentMapperRegistry` | Domain-pure; brokers register at import |
| `MarketFeedPublisher` shared | Dhan + Upstox publish TICK/DEPTH |
| `TracingPort` | Application stops importing infra tracing |
| `runtime.factory.build()` | Single composition root |
| `application/ledger/` | Outbox + fill ingress (extract from OMS) |
| Shadow portfolio projection | Compare with OrderManager book |
| Unified Upstox reconciliation | Delegates to `ReconciliationEngine` |
| Feature flags | `TRADEX_LEDGER_AUTHORITY`, `TRADEX_UNIFIED_ROOT` |

### Tasks (selected — full list in backlog)

| Task ID | Description | Deps | Complexity | Maps |
|---------|-------------|------|------------|------|
| TRANS-P5-010 | Upstox EventBus tick publish | P3, ADR-016 | M | AUDIT-003 |
| TRANS-P5-011 | Segment mapper registry | P3, ADR-014 | M | AUDIT-004 |
| TRANS-P5-012 | Unify Upstox reconciliation | P2-011 | M | AUDIT-005 |
| TRANS-P5-013 | Fail-closed market data semantics | P5-010 | M | AUDIT-010 |
| TRANS-P5-020 | Tracing port + DI | P3-008 | M | AUDIT-007 |
| TRANS-P5-021 | `runtime.factory.build()` single root | P1, ADR-017 | L | AUDIT-008 |
| TRANS-P5-022 | Migrate SDK/CLI/API to factory | P5-021 | L | AUDIT-008 |
| TRANS-P5-030 | Ledger outbox as write boundary | ADR-015 | L | AUDIT-014 |
| TRANS-P5-031 | Shadow portfolio projection | P5-030 | L | AUDIT-014 |
| TRANS-P5-032 | Deepen reconciliation economics | P5-012 | M | AUDIT-009 |
| TRANS-P5-033 | Dynamic gateway factory from entry points | P5-011 | M | AUDIT-013 |
| TRANS-P5-034 | Event envelope metadata | P1-004 | M | AUDIT-016 |
| TRANS-P5-035 | Mode parity: backtest explicit mode | P2-013 | S | AUDIT-011 |
| TRANS-P5-040 | Remove shims at zero usage | P5-022,031 | M | ongoing |

### Acceptance criteria

- [ ] `lint-imports` green after every P5 PR
- [ ] `test_flow_contracts.py` all pass (no xfails)
- [ ] Upstox certification includes bus tick check (golden fixture)
- [ ] Shadow projection parity report: 0 drift on 24h replay fixture
- [ ] `process_context` duplicate registration: impossible via factory (not just warn)
- [ ] Paper + replay parity tests blocking in CI
- [ ] Feature flags documented; default safe (ledger shadow off until certified)

### Risks

| Risk | Mitigation |
|------|------------|
| Ledger migration breaks live | Shadow mode; flag `TRADEX_LEDGER_AUTHORITY=0` default until certified |
| Single root breaks API | Integration test: API+CLI same OMS instance |
| Large PRs | One task = one PR; max 500 LOC where possible |

### Exit criteria → Phase 6 & 7

- [ ] All P5 tasks complete or explicitly deferred with ADR
- [ ] Flow contract tests green
- [ ] Live-readonly certification tier passes (env permitting)
- [ ] Shim removal conditions met or scheduled

---

## Phase 6 — Feature Delivery

### Objective

Deliver **independent, releasable business capabilities** on top of the stabilized platform. Each capability uses command handlers and projections — no bypass of OMS/ledger.

### Scope

Capabilities (each = epic with own acceptance):

| Capability | Key modules | Release flag |
|------------|-------------|--------------|
| Market Access | instruments, subscriptions, historical | `CAP_MARKET_ACCESS` |
| Trading | place/cancel/modify, risk, slices | `CAP_TRADING` |
| Options | chains, greeks, multi-leg | `CAP_OPTIONS` |
| Portfolio | holdings, PnL, allocations | `CAP_PORTFOLIO` |
| Analytics | scanner, strategy, signals | `CAP_ANALYTICS` |
| Replay | deterministic replay API | `CAP_REPLAY` |
| Strategy Engine | orchestrator, scheduling | `CAP_STRATEGY` |
| AI Agents | `interface/agent` guardrails | `CAP_AGENT` |

### Deliverables

Per capability:
- Capability ADR
- Command/query handlers (CQRS)
- Contract tests
- CLI + MCP exposure
- User documentation
- Certification extension (if broker-touching)

### Tasks (epic level)

| Task ID | Description | Deps | Complexity |
|---------|-------------|------|------------|
| TRANS-P6-001 | Market Access v1 (unified subscribe API) | P5 | L |
| TRANS-P6-002 | Trading v1 (command-only placement) | P5 | L |
| TRANS-P6-003 | Options v1 (chain + single-leg) | P6-001 | L |
| TRANS-P6-004 | Portfolio v1 (projection reads) | P5-031 | M |
| TRANS-P6-005 | Analytics v1 (scanner determinism) | P5-035 | M |
| TRANS-P6-006 | Replay v1 (API + CLI) | P5 | M |
| TRANS-P6-007 | Strategy Engine v1 (orchestrator hardening) | P6-002 | L |
| TRANS-P6-008 | AI Agents v1 (tool surface on commands) | P6-002, P4 | M |

### Acceptance criteria (per capability)

- [ ] Capability ADR accepted
- [ ] No direct broker imports in application/analytics
- [ ] Contract tests pass
- [ ] CLI `broker verify` includes capability checks
- [ ] Feature flag off = capability disabled loud (not silent)
- [ ] Documentation in Handbook appendix

### Risks

| Risk | Mitigation |
|------|------------|
| Feature bypasses ledger | Architecture test: no `OrderManager` import from analytics |
| Options complexity | P6-003 scoped to single-leg first |

### Exit criteria → Phase 7

- [ ] Minimum viable capabilities: Market Access, Trading, Portfolio, Replay
- [ ] All P6 epics have certification evidence (paper tier minimum)

---

## Phase 7 — Production Hardening

### Objective

Operational excellence for institutional deployment: SLOs, chaos, load, security, observability, runbooks.

### Scope

- Performance SLOs (tick lag, ack latency, recon age)
- Chaos + load tests (blocking in production gate)
- Recovery runbooks
- OpenTelemetry tracing end-to-end
- Security hardening audit
- Multi-process deployment guidance (or explicit single-writer enforcement)

### Deliverables

| Artifact | Path |
|----------|------|
| SLO document | `docs/operations/SLO.md` |
| Runbooks | `docs/operations/runbooks/` |
| Chaos suite expansion | `tests/chaos/` |
| Load test in CI (paper) | `load-test.yml` repaired |
| Security audit report | `docs/reviews/security-YYYY-MM-DD.md` |
| Production gate v2 | `production_gate.yml` all blocking |

### Tasks

| Task ID | Description | Deps | Complexity |
|---------|-------------|------|------------|
| TRANS-P7-001 | Define SLOs + alerting thresholds | P5, P6 | M |
| TRANS-P7-002 | OTel tracing through command handlers | P5-020 | M |
| TRANS-P7-003 | Chaos: WS disconnect, UNKNOWN flood, recon drift | P5 | L |
| TRANS-P7-004 | Load test: 1000 instruments paper | P5-010 | M |
| TRANS-P7-005 | Recovery runbooks (restart, token, recon) | P2 | M |
| TRANS-P7-006 | Security audit + bandit/safety blocking | P3 | M |
| TRANS-P7-007 | Production gate: all tiers blocking | P4, P6 | M |
| TRANS-P7-008 | Deployment topology ADR (single-writer) | P5-030 | S |
| TRANS-P7-009 | Live certification required for release/** | ADR-018 | S |

### Acceptance criteria

- [ ] SLOs measured in staging for 7 days
- [ ] Chaos suite passes in production gate
- [ ] Load test meets latency thresholds (paper)
- [ ] Runbooks reviewed by operator
- [ ] Release to `release/**` requires live-readonly cert artifact
- [ ] No HIGH bandit findings in `src/`

### Risks

| Risk | Mitigation |
|------|------------|
| Live chaos too risky | Paper/sandbox only in CI; live manual runbook |
| SLO data unavailable | Instrument in P7-002 first |

### Exit criteria (program complete)

- [ ] Institutional readiness review passed
- [ ] All Phase 0–7 exit criteria met
- [ ] Risk register items closed or accepted with ADR
- [ ] Success criteria in README.md § Success criteria — all checked