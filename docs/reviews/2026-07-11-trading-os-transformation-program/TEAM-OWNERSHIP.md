# Team Ownership & Parallel Work Rules

Enables multiple engineers or AI agents to work independently without architectural drift.

---

## Ownership lanes

| Lane | DRI title | Owns `src/` paths | Owns tests | Forbidden |
|------|-----------|-------------------|------------|-----------|
| **L1 Domain & Contracts** | Domain Architect | `domain/**` | `tests/unit/domain/` | `brokers`, `infrastructure`, `interface` |
| **L2 Market Data** | MD Lead | `brokers/*/websocket`, `application/streaming`, MD publishers | `tests/**/market*`, `test_*stream*` | OMS order placement |
| **L3 OMS / Execution** | OMS Lead | `application/oms`, `application/execution`, `application/ledger` (P5) | `tests/component/oms/` | Broker wire, UI |
| **L4 Broker Platform** | Broker Lead | `brokers/**` (except shared policy in L2) | `tests/unit/brokers`, `tests/integration/brokers` | `domain` entity definitions |
| **L5 Runtime / Platform** | Platform Lead | `runtime/**`, `infrastructure/gateway`, `infrastructure/di` | `tests/unit/runtime`, `tests/component/runtime` | Feature logic in UI |
| **L6 Integration / Release** | Release Lead | `.github/**`, `scripts/audit`, `scripts/verify`, `pyproject.toml` lint | `tests/architecture/` | Production feature code |
| **L7 Quant / Research** | Quant Lead | `analytics/**`, `datalake/**` (research) | `tests/unit/analytics/` | `application.oms`, `brokers` |

**Presentation** (`interface/**`): shared — API/UI/agent changes require L5 review for composition calls.

---

## Parallel work matrix

| Can run in parallel | Must be sequential |
|---------------------|-------------------|
| P1 docs (L1) + P3 CI (L6) | P5-030 ledger before P5-031 shadow |
| P2 flows (L1,L3) + P3 CI (L6) | P3-008 before P5-011 segment registry |
| P5-010 Upstox bus (L2) + P5-020 tracing (L3) | P5-021 factory before P5-022 migration |
| P6 capabilities (different epics) | P5 complete before P6-002 trading |
| P4 doctor (L4) + P5-012 recon (L4) | P3 complete before any P5 merge to main |

---

## PR rules

1. **One `TRANS-*` task per PR** (exceptions: subtasks P3-008a/b/c)
2. **Lane owner reviews** PRs touching their paths
3. **L6 approval** required for any `pyproject.toml` import-linter change
4. **Chief Architect** approval for ADR status → Accepted
5. PR description template:

```markdown
## Task
TRANS-Px-xxx

## Handbook section
§X.Y

## Bounded context
[Market Data | OMS | ...]

## Tests
- [ ] lint-imports
- [ ] tests/architecture
- [ ] lane-specific suite

## Deployable
- [ ] Feature flag default safe
- [ ] Rollback documented
```

---

## Conflict resolution

| Conflict type | Resolver |
|---------------|----------|
| Boundary dispute | Chief Architect + ADR |
| Test ownership overlap | L6 assigns marker |
| Broker vs domain type location | L1 decides; types live in `domain/` |
| CI gate blocking merge | L6; no `continue-on-error` override without ADR |

---

## AI agent assignment heuristic

```
if task.startswith("TRANS-P3"): assign L6
elif "segment" in task or "domain" in task: assign L1
elif "bus" in task or "subscription" in task: assign L2
elif "ledger" in task or "OMS" in task: assign L3
elif "wire" in task or "certif" in task: assign L4
elif "factory" in task or "runtime" in task: assign L5
elif "scanner" in task or "backtest" in task: assign L7
```

Agents must read `docs/architecture/HANDBOOK.md` (once P1 complete) before code changes.

---

## Communication cadence

| Ceremony | Frequency | Output |
|----------|-----------|--------|
| Program sync | Weekly | Milestone RAG, blockers |
| Architecture office hours | Biweekly | ADR decisions |
| Lane standup | Daily async | Task status in backlog |
| Evidence update | Per milestone | `docs/reviews/` appendix |