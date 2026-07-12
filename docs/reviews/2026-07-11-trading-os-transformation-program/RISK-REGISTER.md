# Risk Register

| ID | Risk | Prob | Impact | Phase | Mitigation | Owner |
|----|------|------|--------|-------|------------|-------|
| R-001 | CI path drift recurs after fixes | M | H | P3 | `test_workflow_paths.py` | Integration |
| R-002 | Phase 5 ledger migration breaks live orders | M | C | P5 | Shadow mode + feature flag default off | OMS |
| R-003 | Single composition root breaks API/CLI | M | H | P5 | E2E shared OMS test before cutover | Runtime |
| R-004 | Upstox bus fix changes listener behavior | L | M | P5 | Golden fixture + parallel run | Market Data |
| R-005 | Live certification unavailable in CI | H | M | P4,P7 | Tier semantics; blocked ≠ pass | Integration |
| R-006 | Engineers bypass ledger during P5 | M | H | P5 | Arch test: no OrderManager bypass from UI | Chief Architect |
| R-007 | Handbook/docs diverge from code | M | M | P1+ | PR template requires handbook cite | Domain |
| R-008 | Import-linter fix blocked by tracing coupling | M | M | P3 | TracingPort in P3-008b before merge | OMS |
| R-009 | Multi-process deployment corrupts SQLite OMS | L | C | P7 | ADR-020 single-writer enforcement | Ops |
| R-010 | HTTP retry duplicates live orders | M | C | P5,P7 | AUDIT-017 chaos test | Broker |
| R-011 | Phase 6 features bypass command handlers | M | H | P6 | Arch tests per capability | Integration |
| R-012 | AI agents implement speculative abstractions | M | M | All | YAGNI in Handbook; ponytail review on >500 LOC | Chief Architect |
| R-013 | refactor branch diverges from main | H | M | All | Weekly merge main → branch; P3 first on main | Integration |
| R-014 | Market hours block WS certification | H | L | P4,P7 | `FORCE_MARKET_OPEN` + recorded fixtures | Broker |
| R-015 | Collection errors hide regressions | M | M | P3 | Drive to zero; fail CI on collection error | Integration |
| R-016 | Duplicate mutation workflows waste CI | H | L | P3 | Consolidate mutation_testing + nightly | Integration |
| R-017 | Reconciliation economics change broker contracts | M | M | P5 | Version recon DTO; broker adapter tests | OMS |
| R-018 | Event envelope migration breaks consumers | M | H | P5 | schema_version + dual-publish period | Domain |
| R-019 | Operator trusts paper cert for live | M | C | P7 | ADR-018 tier labels on release artifact | Ops |
| R-020 | Scope creep in Phase 5 | M | M | P5 | Task IDs only; no drive-by refactors | Chief Architect |

**Probability:** L/M/H · **Impact:** L/M/H/C(critical)

---

## Risk response by phase

| Phase | Top risks | Gate |
|-------|-----------|------|
| P1 | R-007 | Architecture review checklist |
| P3 | R-001, R-008, R-015 | CI green on main |
| P5 | R-002, R-003, R-006, R-010 | Shadow ledger + E2E |
| P6 | R-011 | Per-capability ADR |
| P7 | R-009, R-019 | Institutional readiness review |

---

## Deferred / accepted risks (require ADR)

| Item | Defer until | Exit criteria |
|------|-------------|---------------|
| Multi-region active-active | Post-P7 | Not in scope |
| Zerodha broker | Never | ADR-013 |
| Full event sourcing migration | Post ledger shadow parity | ADR-015 metrics |
| MyPy strict entire codebase | P7 | Error count zero |