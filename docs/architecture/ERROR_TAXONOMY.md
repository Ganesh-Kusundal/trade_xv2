# Error Taxonomy

**Version:** 1.0 (TRANS-P2-014)  
**Status:** Phase 2 — Loud / Silent / Blocked / Degraded Classification  
**Source:** [Architecture audit §5](../reviews/2026-07-11-trading-os-architecture-audit/05-findings-and-contract.md), [§2 runtime flows](../reviews/2026-07-11-trading-os-architecture-audit/02-runtime-flows.md)  
**Owner:** Domain & Contracts / Chief Architect

---

## Purpose

Trade_XV2 follows a **fail-closed** operations model ([HANDBOOK.md](./HANDBOOK.md) principle 5): empty, stale, `UNKNOWN`, and unavailable must be **distinct** and **observable**. This taxonomy classifies every failure mode so operators, agents, and CI can reason about blast radius.

**Principle:** Silent failures are **technical debt** until remediated. New code must default to **LOUD** or **BLOCKED**, not silent absorption.

Cross-reference: [FLOWS.md](./FLOWS.md), [STATE_MACHINES.md](./STATE_MACHINES.md).

---

## Categories

### LOUD

Failure is **visible** to operators through at least one of:

- Raised exception (`ConnectError`, `ProductionReadinessError`, `IllegalTransitionError`)
- Structured log at `WARNING` or `ERROR`
- Metric increment (e.g. `dhan_ws_dropped_ticks_total`)
- Domain event (`RECONCILIATION_DRIFT`, `KILL_SWITCH_TOGGLED`)
- DLQ entry (`infrastructure/event_bus/event_bus.py`)
- Health probe failure (`HealthState.DEGRADED` with detail)

**Operator action:** Investigate immediately or acknowledge known condition.

### SILENT (debt)

Failure is **absorbed** without reaching consumers, readiness gates, or risk engines. Counted metrics alone without bus events do **not** qualify as loud for downstream systems.

**Operator action:** Treat as defect; maps to AUDIT backlog item. Do not build features assuming this behavior.

### BLOCKED

Operation **refused**; system fail-closed. Caller receives explicit error or gate denial. No partial mutation of trading state.

**Operator action:** Fix precondition (auth, recon, kill-switch, mode) before retry.

### DEGRADED

Partial function continues with **explicit** degraded state. Must be queryable via health, provenance flags, or `BootstrapStatus.DEGRADED`.

**Operator action:** Continue with caution; monitor for escalation to BLOCKED.

---

## Decision matrix

| Question | LOUD | SILENT | BLOCKED | DEGRADED |
|----------|------|--------|---------|----------|
| Can trading continue safely? | Maybe | Unknown | No (for that action) | Partially |
| Is consumer notified? | Yes | No | N/A (prevented) | Via health/events |
| Retry without fix safe? | Case-by-case | **No** | **No** | Case-by-case |
| Acceptable in production? | Yes (visible) | **No** (debt) | Yes (fail-closed) | Yes (with monitoring) |

---

## Classification by subsystem

### Market data

| Scenario | Category | Evidence | Target |
|----------|----------|----------|--------|
| Zero/missing LTP tick drop | **SILENT** | `brokers/dhan/websocket/publish.py:44-48` | **LOUD** + `SubscriptionDegraded` (AUDIT-010) |
| `event_bus=None` publish no-op | **SILENT** | `publish.py:38-39` | **BLOCKED** at subscribe (AUDIT-010) |
| Symbol map fail → `security_id` fallback | **SILENT** / partial | `brokers/dhan/websocket/_helpers.py` | **LOUD** error (MD-5) |
| Upstox ticks not on EventBus | **SILENT** | `market_data_v3.py` L89-97 | **LOUD** bus publish (AUDIT-003) |
| WS disconnect + reconnect | **LOUD** | `ReconnectingServiceMixin` | — |
| Rate-limit admission | **DEGRADED** | Connect blocked, logged | — |
| Stale tick beyond SLA | **DEGRADED** | `FreshnessState.STALE` | — |
| API WS drop-oldest | **SILENT** | Finding C-05 | Resync protocol |

### Order management

| Scenario | Category | Evidence | Target |
|----------|----------|----------|--------|
| Ambiguous broker submit timeout | **LOUD** + **BLOCKED** retry | `order_lifecycle.py:135-157` | — |
| UNKNOWN blocks same `correlation_id` | **BLOCKED** | `idempotency_guard.py:51-57` | — |
| Risk reject | **LOUD** + **BLOCKED** | `risk_manager.py` | — |
| Kill-switch active | **BLOCKED** | `order_lifecycle.py:316` | — |
| Placement gate (recon not ready) | **BLOCKED** | `context.py:416-419` | — |
| `event_bus=None` order publish | **SILENT** | `order_manager.py:389-390` | Fail-closed |
| Duplicate in-flight correlation | **BLOCKED** | `idempotency_guard.py:63-64` | — |
| HTTP retry on ambiguous order write | **LOUD** if duplicate | Finding B-07 | AUDIT-017 chaos test |

### Fills and portfolio

| Scenario | Category | Evidence | Target |
|----------|----------|----------|--------|
| Duplicate fill (same `trade_id`) | **LOUD** (skipped) | `trade_recorder.py`, `ProcessedTradeRepository` | — |
| Trade-before-order buffer overflow | **SILENT** | `trade_recorder.py:104-116` | DLQ + alert (FP-4) |
| Handler exception on bus | **LOUD** (DLQ) | `event_bus.py` | — |
| Dual book OMS vs ledger drift | **SILENT** until recon | AUDIT-014 | Shadow projection |
| Position from broker poll | **BLOCKED** (design) | `OBJECT_MODEL.md` invariant | — |

### Reconciliation

| Scenario | Category | Evidence | Target |
|----------|----------|----------|--------|
| Drift detected (status/qty) | **LOUD** | `reconciliation_service.py:169-173` | — |
| PnL / avg-price drift missed | **SILENT** | `reconciliation_engine.py` shallow compare | AUDIT-009 |
| Loop exception | **DEGRADED** | `reconciliation_service.py:156-158` | — |
| `auto_repair=False` | **LOUD** log, no heal | Default detect-only | Policy-driven |
| Thread join timeout on shutdown | **DEGRADED** | `reconciliation_service.py:99-104` | — |
| Upstox duplicate recon logic | **SILENT** divergence risk | `brokers/upstox/reconciliation/service.py` | AUDIT-005 |

### Bootstrap and operations

| Scenario | Category | Evidence | Target |
|----------|----------|----------|--------|
| Missing credentials | **LOUD** + **BLOCKED** | `ConnectError`, `REAUTH_REQUIRED` | — |
| Production readiness fail | **BLOCKED** | `production_readiness.py` | — |
| Parity gate skip | **SILENT** | `SKIP_PARITY_GATE=1` | **BLOCKED** in prod (AUDIT-002) |
| Parity script wrong path | **SILENT** / fail | `parity_gate.py` L30-40 | AUDIT-002 |
| CI `continue-on-error` safety steps | **SILENT** | Finding B-06 | AUDIT-006 |
| Duplicate `TradingContext` | **LOUD** (warn) | `process_context.py` | **BLOCKED** (AUDIT-008) |
| SQLite multi-process OMS | **SILENT** corruption risk | Finding A-07 | Deployment guard |
| Session kernel wire failure swallowed | **SILENT** | `session.py:314-319` | **LOUD** |

### Mode and parity

| Scenario | Category | Evidence | Target |
|----------|----------|----------|--------|
| `market` mode order attempt | **BLOCKED** | `session.py:211-214` | — |
| `trade` without process OMS | **BLOCKED** | `session.py:380-391` | — |
| `PURE_SIM` backtest assumed live | **SILENT** | `backtest/engine.py` | Explicit flag (AUDIT-011) |
| Orchestrator dry-run default | **BLOCKED** (placement) | `ORCHESTRATOR_DRY_RUN=1` | Safe default |
| Paper cert treated as live cert | **SILENT** | MP-4 contract | CI enforcement |

---

## AUDIT finding mapping

| AUDIT ID | Title | Primary category | Secondary | TRANS backlog | Flow / doc |
|----------|-------|------------------|-----------|---------------|------------|
| **AUDIT-001** | CI workflow path drift | **SILENT** (false green) | LOUD in logs | TRANS-P3-001 | §1, §10 |
| **AUDIT-002** | Replay verifier broken path | **SILENT** (when skipped) | BLOCKED when enforced | TRANS-P3-002 | §1, §10 |
| **AUDIT-003** | Upstox EventBus tick publish | **SILENT** | — | TRANS-P5-010 | §6 |
| **AUDIT-004** | Domain broker imports (segment mapper) | **LOUD** (when lint runs) | BLOCKED at registry | TRANS-P5-011 | §4 |
| **AUDIT-005** | Unify reconciliation compare | **SILENT** (drift miss) | — | TRANS-P5-012 | §9 |
| **AUDIT-006** | Safety gates non-blocking in CI | **SILENT** | — | TRANS-P3-004 | Ops |
| **AUDIT-007** | Tracing port / app→infra imports | **LOUD** (lint) | — | TRANS-P5-020 | Layering |
| **AUDIT-008** | Single composition root | **LOUD** (warn today) | BLOCKED (target) | TRANS-P5-021 | §1, §11 |
| **AUDIT-009** | Reconciliation economics | **SILENT** | — | TRANS-P5-032 | §9 |
| **AUDIT-010** | Fail-closed market data | **SILENT** (current) | LOUD (target) | TRANS-P5-013 | §6 |
| **AUDIT-011** | Mode parity certification | **SILENT** | DEGRADED | TRANS-P5-035 | §11 |
| **AUDIT-012** | Dhan regression suite missing | **LOUD** (workflow fail) | — | TRANS-P3-007 | Ops |
| **AUDIT-013** | Dynamic gateway factory | — | — | TRANS-P5-033 | §4 |
| **AUDIT-014** | Ledger shadow projection | **SILENT** | — | TRANS-P5-031 | §8 |
| **AUDIT-015** | Stale import-linter ignores | **SILENT** | — | TRANS-P3-008 | Layering |
| **AUDIT-016** | Event envelope metadata | **SILENT** | — | TRANS-P5-034 | Events |
| **AUDIT-017** | HTTP order write idempotency | **LOUD** (if duplicate) | SILENT (until chaos) | TRANS-P5-* | §7 |

### Ranked findings crosswalk (A/B/C → taxonomy)

| Ranked ID | Finding | Category | AUDIT |
|-----------|---------|----------|-------|
| A-01 | CI paths broken | SILENT → operators | AUDIT-001 |
| A-02 | Upstox no bus ticks | SILENT | AUDIT-003 |
| A-03 | Domain broker imports | LOUD (CI) | AUDIT-004 |
| A-04 | No authoritative fill spine | DEGRADED / SILENT | AUDIT-014 |
| A-05 | Shallow reconciliation | SILENT | AUDIT-005, AUDIT-009 |
| A-06 | Parity gate broken + skippable | SILENT | AUDIT-002 |
| A-07 | SQLite multi-process | SILENT | — |
| B-04 | Multi composition roots | LOUD (warn) | AUDIT-008 |
| B-06 | Warn-only CI gates | SILENT | AUDIT-006 |
| B-07 | HTTP retry duplicates | LOUD (outcome) | AUDIT-017 |
| C-05 | API WS drop-oldest | SILENT | AUDIT-010 |

---

## Contract clause mapping

Expected behavior contract from audit §5:

| Clause | Violation category | Current | Remediation AUDIT |
|--------|-------------------|---------|-------------------|
| MD-3 | SILENT | Upstox no bus | AUDIT-003 |
| MD-4 | SILENT | Counter only on drop | AUDIT-010 |
| MD-5 | SILENT | security_id fallback | AUDIT-010 |
| FP-4 | SILENT | Buffer overflow | AUDIT-010 / trade recorder |
| RC-1 | SILENT | Shallow compare | AUDIT-009 |
| MP-3 | SILENT | `SKIP_PARITY_GATE` | AUDIT-002 |
| OP-1 | SILENT | Warn-only CI | AUDIT-006 |
| OM-2 | BLOCKED | UNKNOWN retry | ✅ Correct |
| RC-5 | BLOCKED | Placement gate | ✅ Correct |
| OP-3 | BLOCKED | Kill-switch | ✅ Correct |

---

## UNKNOWN error handling (normative)

`UNKNOWN` is a **LOUD** + **BLOCKED** combination:

| Aspect | Classification | Rationale |
|--------|----------------|-----------|
| Synchronous `OrderResult` | **LOUD** | Caller sees `success=False`, `SubmissionState.UNKNOWN` |
| `ORDER_UPDATED` event | **LOUD** | Observers notified |
| Retry same `correlation_id` | **BLOCKED** | Prevents duplicate broker exposure |
| Expedited reconciliation | **DEGRADED** until resolved | Trading gated by placement policy |
| Resolution transition | **LOUD** | `UNKNOWN → OPEN|REJECTED|CANCELLED` emits event |

See [STATE_MACHINES.md](./STATE_MACHINES.md) § Order — UNKNOWN rules U-1 … U-8.

---

## Fail-closed rules (target contract)

New implementations and remediations must satisfy:

| Rule | Description |
|------|-------------|
| **FC-1** | `event_bus=None` at subscribe or place → raise, not no-op |
| **FC-2** | Tick drop → metric **and** `SubscriptionDegraded` event |
| **FC-3** | Instrument mapping failure → error, not wire-id fallback |
| **FC-4** | `UNKNOWN` never returns `success=True` without reconciliation |
| **FC-5** | Production boot cannot skip parity gate |
| **FC-6** | CI safety steps are BLOCKED on failure, not warn-only |
| **FC-7** | Empty broker read → error distinct from "no data yet" |
| **FC-8** | One `TradingContext` per process — duplicate is BLOCKED |

---

## Observability hooks

| Mechanism | Module | Category emitted |
|-----------|--------|------------------|
| Structured audit events | `infrastructure/observability/audit.py` | LOUD (`emit_degraded_mode`) |
| Auth metrics | `infrastructure/auth/metrics.py` | LOUD |
| DLQ | `infrastructure/event_bus/event_bus.py` | LOUD |
| Health snapshots | `domain/lifecycle_health.py`, `stream_health.py` | DEGRADED |
| Provenance `degraded` flag | `application/data/provenance.py` | DEGRADED |
| Bootstrap status | `domain/ports/bootstrap.py` | BLOCKED / DEGRADED |

---

## Usage in code review

When reviewing a PR that handles errors:

1. **Classify** the failure using this taxonomy.
2. If **SILENT**, link a TRANS/AUDIT item or fix in the same PR.
3. If **BLOCKED**, ensure the caller receives actionable remediation text (`ConnectError.remediation`).
4. If **DEGRADED**, ensure health or provenance exposes the state.
5. Update [FLOWS.md](./FLOWS.md) failure table if behavior changes.

---

## References

- [05-findings-and-contract.md](../reviews/2026-07-11-trading-os-architecture-audit/05-findings-and-contract.md) — silent failure matrix
- [07-backlog.md](../reviews/2026-07-11-trading-os-architecture-audit/07-backlog.md) — AUDIT-001 … AUDIT-017
- [ENGINEERING-BACKLOG.md](../reviews/2026-07-11-trading-os-transformation-program/ENGINEERING-BACKLOG.md) — TRANS-P2-014
- [HANDBOOK.md](./HANDBOOK.md) — fail-closed principle
- [GLOSSARY.md](./GLOSSARY.md) — term definitions