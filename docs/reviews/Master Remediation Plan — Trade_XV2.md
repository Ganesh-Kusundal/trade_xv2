# Master Remediation Plan — Trade_XV2

## Executive Summary

**Capstone Verdict**: NOT READY  
**Weighted Score**: 4.7/10  
**Assessment Date**: 2026-06-23  
**Total Findings**: 87 across all 8 audits (18 Critical, 24 High, 28 Medium, 17 Low)

The Trade_XV2 quantitative trading platform has a sound target architecture (domain → infrastructure → application → entry points) with strong OMS unit tests, Decimal risk management, and well-designed reliability primitives (lifecycle, DLQ, circuit breakers). It is **not ready for live capital** because broker fill paths contain silent state corruption bugs: Dhan publishes cumulative fill quantities as incremental trades, Upstox WebSocket events use a payload contract incompatible with the OMS (and never publish TRADE events), paper trading double-applies positions, and the processed trade idempotency ledger is not persisted on the default CLI path — causing duplicate fills after restart via EventLog replay.

---

## Score Card Summary

| Dimension | Score | Verdict | Top Risk |
|---|---|---|---|
| Architecture | 5/10 | Partial | Risk #5 — stale event_bus import |
| Design Quality | 5/10 | Partial | Risk #2 — Upstox WS contract |
| Code Quality | 6/10 | Adequate | Risk #19 — silent event swallow |
| Testing | 6/10 | Partial | Risk #12 — e2e marker no-op |
| Reliability | 5/10 | Partial | Risk #3 — ledger not persisted |
| Scalability | 5/10 | Partial | Risk #14 — single-writer |
| Security | 5/10 | Partial | Risk #16 — MyPy non-blocking |
| Performance | 6/10 | Adequate | — |
| Maintainability | 5/10 | Partial | Risk #20 — shim drift |
| Operational Readiness | 5/10 | Partial | Risk #11 — integration CI |
| **WEIGHTED TOTAL** | **4.7/10** | **NOT READY** | — |

---

## Dependency Graph of Fixes

```
IncompleteLayerMigration (brokers/common shims)
  ↓ blocks
BrokerImportsApplication (paper/upstox/dhan → application.oms)
  ↓ blocks
UpstoxLiveFillPathBroken + PaperDoubleApply + DhanCumulativeFillBug
  ↓ blocks
UntestedLiveBrokerReconciliation
  ↓ causes
ProcessedTradeLedgerNotPersisted
  ↓ causes
EventLogReplayDuplicatesTrades
  ↓ causes
ProductionIncidentAtMarketOpen
```

### Critical Path Dependencies

| # | Blocking Issue | Blocked By | Impact If Unresolved |
|---|----------------|------------|----------------------|
| 1 | Upstox OMS fill integration | Upstox WS canonical Order contract | Live Upstox positions never update |
| 2 | Crash-safe idempotency | ProcessedTradeRepository persistence | Duplicate fills after restart |
| 3 | Paper/live parity | Remove paper double apply_trade | Paper validates wrong strategies |
| 4 | Dhan position accuracy | Incremental fill qty fix | Partial fills double-count |
| 5 | API bootstrap | Fix runtime event_bus import | API server may fail to start |
| 6 | Neutral composition root | Extract from CLI BrokerService | API coupled to CLI internals |
| 7 | Broker adapter purity | Remove application imports from brokers | Hexagonal boundary permanently broken |
| 8 | Live broker CI gate | Make integration job blocking | Regressions reach production |

---

## The Tactical Fix Roadmap

### Phase A: Immediate / Critical (Protect Capital & Data)

**Timeline**: 1–3 days  
**Goal**: Close risks that can cause immediate financial loss or data corruption

| ID | Fix Description | Risk Closed | File Location | Effort |
|----|-----------------|-------------|---------------|--------|
| A1 | Fix Dhan WS: compute incremental fill qty (`filled - order.filled_quantity`) | Risk #1 | `brokers/dhan/websocket.py:991-1001` | 4h |
| A2 | Remove direct `position_manager.apply_trade()` from paper path | Risk #4 | `brokers/paper/paper_orders.py:191` | 2h |
| A3 | Persist ProcessedTradeRepository in oms_setup (SQLite path alongside EventLog) | Risk #3, #6 | `cli/services/oms_setup.py:150-157` | 4h |
| A4 | Fix runtime import: `infrastructure.event_bus.factory.AsyncEventBusFactory` | Risk #5 | `runtime/trading_runtime_factory.py:77` | 1h |
| A5 | Add regression test for Dhan cumulative fill semantics | Risk #1 | `brokers/dhan/tests/unit/test_websocket.py` | 2h |
| A6 | Disable or gate `authorize_risk_fail_open` behind explicit env | Risk #7 | `runtime/trading_runtime_factory.py:49` | 2h |

**Execution Order**: A4 → A1 → A5 → A2 → A3 → A6

---

### Phase B: Structural (Architecture & Boundaries)

**Timeline**: 1–2 weeks  
**Goal**: Fix dependency direction, enforce boundaries, establish live broker event contracts

| ID | Fix Description | Risk Closed | Architecture Impact | Effort |
|----|-----------------|-------------|---------------------|--------|
| B1 | Upstox WS: publish canonical `Order` in ORDER_UPDATED + TRADE events | Risk #2, #9 | Live Upstox path functional | 2d |
| B2 | Remove ORDER_PLACED publish from Upstox order_command_adapter | Risk #9 | Single event source (OMS) | 4h |
| B3 | Decouple paper gateway from TradingContext; inject via composition root | Risk #8 | Broker→application inversion fixed | 1d |
| B4 | Extract neutral `runtime/composition.py` from CLI BrokerService | Risk #15 | API independent of CLI | 2d |
| B5 | Complete shim migration; delete brokers/common re-exports | Risk #20 | Single import path | 1d |
| B6 | Add import-linter contracts for runtime and api layers | — | Enforcement gap closed | 4h |
| B7 | Wire trade ledger cleanup as lifecycle shutdown hook (not attach) | Risk #17 | Deterministic cleanup | 2h |

**Prerequisites**: Phase A must complete first

---

### Phase C: Hardening (Tests & Resilience)

**Timeline**: 2–4 weeks  
**Goal**: Test coverage, CI gates, chaos testing, refactoring

| ID | Fix Description | Risk Closed | Dimensions Improved | Effort |
|----|-----------------|-------------|---------------------|--------|
| C1 | Add `@pytest.mark.e2e` to all e2e tests; fix CI marker step | Risk #12 | Testing +0.3 | 1h |
| C2 | Make integration CI job blocking (remove continue-on-error) | Risk #11 | Testing +0.5, Ops +0.3 | 2h |
| C3 | Add Upstox OMS integration test (portfolio_stream → OrderManager) | Risk #2 | Testing +0.5 | 1d |
| C4 | Add infrastructure/ test suite (lifecycle, observability, event_log) | Risk #13 | Testing +0.5 | 2d |
| C5 | Consolidate duplicate shim/canonical test suites | Risk #20 | Maintainability +0.3 | 1d |
| C6 | Decompose OrderManager into placement/recording/replay services | — | Code Quality +0.5 | 1w |
| C7 | Test multi_strategy_runtime | Risk #17 | Testing +0.3 | 2d |
| C8 | Block MyPy errors incrementally (reduce from 499) | Risk #16 | Security +0.5 | 1w |
| C9 | Add chaos test: WS disconnect during active order + restart replay | Risk #6 | Reliability +0.5 | 2d |
| C10 | Enforce single-writer lock file at TradingContext startup | Risk #14 | Reliability +0.3 | 4h |

**Prerequisites**: Phase B must complete first

---

## Execution Protocol

### Fix Execution Template

```markdown
## Fix [ID]: [Title]

### Context
- **Risk Closed**: Risk [N] from Top 20
- **Root Cause**: [from audit findings]
- **Files Affected**: [list with paths]

### Step 1: Test First (Red)
- [ ] Write failing test demonstrating the vulnerability
- [ ] Verify test fails before fix
- [ ] Test file: `[path/to/test_file.py]`

### Step 2: Isolate
- [ ] Define or clean up interface/port
- [ ] Ensure adapter boundary is respected
- [ ] Interface: `[path/to/interface.py]`

### Step 3: Refactor (Green)
- [ ] Apply fix to production code
- [ ] Verify test passes
- [ ] Production file: `[path/to/production_file.py]`

### Step 4: Verify
- [ ] All existing tests still pass
- [ ] Fix satisfies quant platform criteria
- [ ] Fix satisfies reliability criteria
- [ ] No new linting/type errors
- [ ] Run verification commands below

### Verification Commands
```bash
pytest [test_file] -v
pytest application/oms/tests/ application/execution/tests/ -v --tb=short
lint-imports --config .import-linter.ini
ruff check [fixed_files]
```
```

---

## Example: Fix A1 (Dhan Incremental Fill)

### Context
- **Risk Closed**: Risk #1
- **Root Cause**: `brokers/dhan/websocket.py:991` uses cumulative `filled_quantity` as trade qty; OMS adds to existing filled qty
- **Files Affected**: `brokers/dhan/websocket.py`, `brokers/dhan/tests/unit/test_websocket.py`

### Step 1: Test First (Red)
- Write test: partial fill 40 then 60 cumulative → two TRADE events with qty 40 and 20 (not 40 and 100)
- Test file: `brokers/dhan/tests/unit/test_websocket.py`

### Step 2: Isolate
- OMS contract: TRADE.quantity is always incremental (`application/oms/tests/test_partial_fill_lifecycle.py`)

### Step 3: Refactor (Green)
- Compute `incremental = filled - previous_filled` before publishing TRADE
- Production file: `brokers/dhan/websocket.py:991-1001`

### Step 4: Verify
```bash
pytest brokers/dhan/tests/unit/test_websocket.py -v
pytest application/oms/tests/test_partial_fill_lifecycle.py -v
```

---

## Progress Tracking

### Audit Completion
- [x] Step 1: architecture-reviewer → `docs/reviews/audit-architecture-reviewer.md`
- [x] Step 2: eda-auditor → `docs/reviews/audit-eda-auditor.md`
- [x] Step 3: deep-static-auditor → `docs/reviews/audit-deep-static-auditor.md`
- [x] Step 4: broker-auditor → `docs/reviews/audit-broker-auditor.md`
- [x] Step 5: quant-platform-reviewer → `docs/reviews/audit-quant-platform-reviewer.md`
- [x] Step 6: testing-strategy-auditor → `docs/reviews/audit-testing-strategy-auditor.md`
- [x] Step 7: reliability-readiness-reviewer → `docs/reviews/audit-reliability-readiness-reviewer.md`
- [x] Step 8: production-readiness-reviewer → `docs/reviews/audit-production-readiness-reviewer.md`

### Synthesis
- [x] Master Remediation Plan generated

### Execution (Deferred — audit-only engagement)
- [ ] Phase A: Immediate/Critical fixes (A1–A6)
- [ ] Phase B: Structural fixes (B1–B7)
- [ ] Phase C: Hardening fixes (C1–C10)

---

## Audit Artifacts Index

| Agent | Artifact |
|-------|----------|
| architecture-reviewer | [audit-architecture-reviewer.md](audit-architecture-reviewer.md) |
| eda-auditor | [audit-eda-auditor.md](audit-eda-auditor.md) |
| deep-static-auditor | [audit-deep-static-auditor.md](audit-deep-static-auditor.md) |
| broker-auditor | [audit-broker-auditor.md](audit-broker-auditor.md) |
| quant-platform-reviewer | [audit-quant-platform-reviewer.md](audit-quant-platform-reviewer.md) |
| testing-strategy-auditor | [audit-testing-strategy-auditor.md](audit-testing-strategy-auditor.md) |
| reliability-readiness-reviewer | [audit-reliability-readiness-reviewer.md](audit-reliability-readiness-reviewer.md) |
| production-readiness-reviewer | [audit-production-readiness-reviewer.md](audit-production-readiness-reviewer.md) |
| Progress tracker | [ORCHESTRATION_PROGRESS.md](ORCHESTRATION_PROGRESS.md) |

---

## Re-Certification Criteria

The platform may be re-assessed for CONDITIONALLY READY when:

1. All Phase A fixes complete with passing tests
2. Upstox live fill path functional (B1)
3. ProcessedTradeRepository persisted and verified across restart (A3)
4. Integration CI blocking on all PRs (C2)
5. Weighted score ≥ 6.5 on re-audit

Target READY (≥ 8.0) requires Phase B + C completion and live broker soak test.
