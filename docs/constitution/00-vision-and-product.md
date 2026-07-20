# 00 — Vision & Product Constitution

**Status:** Canonical  
**Authority:** This document is the sole product identity reference for TradeXV2.  
**Supersedes:** Conflicting product statements in any other document.

---

## Identity

**TradeXV2 is an event-driven quantitative trading kernel that supports multiple execution capabilities.**

Execution capabilities include **Replay**, **Backtesting**, **Paper Trading**, and **Live Broker Execution**. All capabilities share the same domain model, execution pipeline, event contracts, and lifecycle. **Live execution is an optional capability** that can remain disabled without changing the architecture.

The kernel pipeline is immutable:

```text
Market Data → Feature Pipeline → Indicators → Strategies → Signals → Risk → OMS → Execution Target
```

**Execution Target** is a capability plug-in, not an architectural fork. The rest of the platform is unaware of which target is active.

---

## Problems Solved

| Problem | How TradeXV2 addresses it |
|---|---|
| Research results that don't match live behavior | Zero-parity: one OMS, one risk gate, one event model across all execution targets |
| Broker lock-in | Broker plugins behind stable ports; composition root selects once at boot |
| Exchange-specific leakage | Exchange/calendar plugins; datalake and domain stay exchange-agnostic |
| Fragmented analytics | Single feature → indicator → strategy → signal pipeline |
| Untrustworthy backtests | Simulated fills go through the same OMS spine as paper and live |
| Operator tooling sprawl | One CLI (`tradex`), API, TUI, MCP over the same kernel |

---

## Problems Not Solved (by design)

- Multi-node / distributed cluster trading (one kernel per process)
- Regulatory compliance automation (SEBI reporting, audit trails beyond event log)
- Portfolio optimization across uncorrelated strategies at scale
- Real-time ML model serving infrastructure
- Order routing across multiple venues simultaneously

---

## Out of Scope

1. A second trading language/stack beyond Python + TypeScript (when Web SPA lands).
2. Speculative brokers/exchanges not behind a registered plugin entry-point.
3. Mocking real-money paths for unit-test convenience (integration tests only).
4. Rewriting the domain model without an ADR.
5. A separate analytics OMS or fill engine per execution mode.
6. String-based broker branching outside the composition root.
7. New UI component libraries beyond what the project already uses.

---

## Capability Matrix

| Capability | Kernel role | Product surface today | Mandatory for kernel | Production-ready bar |
|---|---|---|---|---|
| **Market Data** | Ingest quotes, depth, bars, history | CLI, API, TUI, MCP | Yes | Stable subscriptions, reconnect, quality gates |
| **Feature Pipeline** | Transform raw data → features | Internal | Yes | Deterministic, typed outputs |
| **Indicators** | Compute technical/statistical series | CLI `indicator` | Yes | Parity across batch and stream |
| **Strategies** | Evaluate rules/models → signals | CLI `strategy`, `backtest` | Yes | Same code in all execution targets |
| **Signals** | Typed intent to trade (not yet an order) | Internal | Yes | Immutable, timestamped, attributable |
| **Risk** | Pre-trade gate; authoritative deny | Internal (API `/risk` read-only) | Yes | Fail-closed; no bypass on hot path |
| **OMS** | Order lifecycle authority | Internal | Yes | FSM enforced; idempotent place |
| **Replay** | Deterministic historical re-run | CLI `analytics replay` | Yes (research trust) | Same event stream on re-run |
| **Backtest** | Batch strategy evaluation | CLI `backtest` | Yes (research trust) | Equity curve reproducible |
| **Paper** | Simulated live with real-time data | CLI `analytics paper` | Yes (research trust) | Fill model documented; zero-parity with replay |
| **Live Broker** | Real venue submission | **Disabled** (capability exists in kernel) | No (optional) | Auth, reconcile, kill-switch, durable idempotency |

**Key rule:** Mandatory capabilities must work and be tested even when Live is disabled. Live adds operational requirements; it does not add a second architecture.

---

## Product Surfaces

| Surface | Role |
|---|---|
| `tradex` CLI | Primary operator interface for research and session management |
| FastAPI (`src/interface/api`) | HTTP API for automation and Web backend |
| Textual TUI | Interactive terminal dashboard |
| MCP servers | Agent/tool integration for datalake and market data |
| Web SPA (`web/`) | Planned; not yet implemented |

Surfaces **select** execution capability at session start. They do **not** embed business logic.

---

## Immutable Product Principles

1. **Zero-parity** — Replay, Backtest, Paper, and Live share identical OMS, Risk, and event semantics. Only the Execution Target adapter differs.
2. **Single composition root** — One place wires concrete brokers, execution targets, and config.
3. **Risk is authoritative** — A deny is final; no venue call after deny.
4. **Domain purity** — Business rules live in domain/application; not in interface or brokers.
5. **Capability, not fork** — Adding Live does not fork strategy, risk, or portfolio code.
6. **Research trust first** — Backtest/replay/paper must be trustworthy before Live ships.

---

## Definition of Production Ready

### Per capability

| Capability | Production ready means |
|---|---|
| Market Data | Reconnect without manual intervention; stale-data detection; subscription limits respected |
| Replay / Backtest | Deterministic re-run produces identical order/fill stream (timestamps from injected clock) |
| Paper | Real-time data + simulated fills through OMS; fill model documented |
| Risk | Fail-closed on provider fault; daily-loss gate correct; kill-switch atomic |
| OMS | Order FSM enforced; idempotent place by correlation_id; reconciliation heals drift |
| Live | All of the above **plus**: durable idempotency across restart, broker reconcile on hot path, auth fail-closed, operational runbooks |

### Platform-wide gates

- `venv/bin/pytest` full suite green (architecture + import-linter + coverage)
- Coverage ≥ 80 overall, ≥ 85 brokers, ≥ 90 OMS
- `graphify update .` current after code changes
- No P0 gaps open in `07-gap-analysis.md`

---

## Success Criteria (verifiable)

1. Operator can scan a universe, inspect analytics, and backtest a strategy end-to-end from CLI.
2. Same strategy code runs in backtest, replay, and paper without modification.
3. Switching execution target requires only composition-root config change.
4. Architecture tests enforce dependency rules and single-bus/single-OMS invariants.
5. Glossary terms (`00b-glossary.md`) used consistently across all modules.

---

## Document Map

| Doc | Role |
|---|---|
| `00b-glossary.md` | Ubiquitous language |
| `01-architecture-constitution.md` | Principles and constraints |
| `01a-quality-attribute-scenarios.md` | Measurable QA acceptance |
| `02-system-blueprint.md` | Behavioral flows |
| `02a-runtime-execution-model.md` | Lifecycle, threads, sync |
| `03-domain-model.md` | Aggregates and events |
| `04-component-contracts.md` | Protocol seams |
| `05-bounded-contexts.md` | Context boundaries |
| `06-reference-architecture.md` | Repo layout |
| `07-gap-analysis.md` | Code vs constitution |
| `08-incremental-implementation.md` | Rebuild playbook |
