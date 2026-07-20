# 01 — Architecture Constitution

**Status:** Canonical  
**Terms:** See `00b-glossary.md`  
**Product identity:** See `00-vision-and-product.md`

---

## 1. Purpose

This document defines the immutable architectural rules for TradeXV2. Every design decision, code review, and gap analysis is measured against the principles and constraints here. Measurable performance targets live in `01a-quality-attribute-scenarios.md`.

---

## 2. Architectural Vision

TradeXV2 is a **single-process, event-driven trading kernel** with:

- **Ports and adapters** at every external boundary (brokers, storage, clocks, execution targets)
- **One message spine** (EventBus) for cross-context integration
- **One composition root** that assembles concrete implementations
- **Capability-based execution** — Replay, Backtest, Paper, Live are interchangeable targets behind one contract
- **Domain-centric design** — business rules and FSMs live in domain/application; infrastructure is dumb adapters

Reference style: NautilusTrader runtime contracts (kernel, cache, engines) adapted to TradeXV2's Python layering — **not** a Nautilus fork.

---

## 3. Immutable Principles

| ID | Principle | Violation symptom |
|---|---|---|
| **P1** | Zero-parity: one OMS + one Risk path for all execution targets | Separate place_order impls per mode |
| **P2** | Single composition root: only `runtime/` imports concrete brokers/plugins | `application` or `interface` importing `brokers.dhan` |
| **P3** | Domain purity: `domain/` imports stdlib + itself only | Domain importing infrastructure |
| **P4** | Risk authoritative: deny stops the pipeline; no venue call after deny | Bypass, getattr kill-switch, swallowed lookup errors |
| **P5** | Execution Target is a capability plug-in, not a fork | Duplicate strategy/risk/portfolio per mode |
| **P6** | Single EventBus: one port, one runtime implementation | Parallel bus implementations |
| **P7** | Single idempotency authority for order correlation | Multiple dedupe stores on hot path |
| **P8** | Clock injection: no `datetime.now()` in fill/order/event builders | Nondeterministic replay |
| **P9** | Order FSM enforced: illegal transitions raise | `with_status` bypass |
| **P10** | Reconciliation on hot path: heal on ORDER_UPDATED/TRADE_APPLIED, not timer-only | Detached reconcile as sole healer |
| **P11** | Fail-closed: unrecoverable invariant violation halts; recoverable retries with backoff | Silent swallow, optimistic continue |
| **P12** | Broker selected once at boot by `BrokerId` enum, never string branching | Scattered `if broker == "dhan"` |

---

## 4. Decision-Making Principles

1. **Correctness over cleverness** — if a flow needs more than two local fixes, redesign the flow.
2. **Deletion over addition** — remove duplicate paths before adding abstractions.
3. **Contracts before contexts** — define the seam (protocol) before drawing module boundaries.
4. **Behavior before classes** — specify flows and state transitions before naming types.
5. **Integration tests over mocks** — real components, real wiring; no mock broker on money paths.
6. **Evolutionary refactor** — no rewrite; each phase leaves the system deployable and testable.
7. **ADR for invariant changes** — changing P1–P12 requires an architecture decision record.

---

## 5. Quality Attributes (intent only)

Scenarios and acceptance thresholds: `01a-quality-attribute-scenarios.md`.

| Attribute | Intent |
|---|---|
| **Latency** | Indicator/strategy evaluation keeps pace with market data feed for configured universe size |
| **Scalability** | Universe and history depth scale via batching and datalake; single-process kernel |
| **Extensibility** | New broker, exchange, strategy, execution target via plugin entry-point — no core edit |
| **Observability** | Every order state transition and risk decision emits traceable events + structured logs |
| **Resiliency** | Transient broker/network faults retry with circuit breaker; no duplicate orders |
| **Recoverability** | Restart reloads durable state; reconcile heals drift before next trade |
| **Determinism** | Replay/backtest: same inputs + clock ⇒ identical event stream |
| **Testability** | Architecture tests enforce layering; parity tests enforce zero-parity |

---

## 6. Architectural Constraints

1. **One kernel per process** — no multi-node design in this constitution.
2. **Python 3.11+** — project venv at `venv/` for all execution and testing.
3. **Indian market first** — NSE/IST via exchange plugin; no hardcoded calendar in datalake core.
4. **DuckDB datalake** — market history and analytics queries; single connection-source boundary.
5. **No second trading stack** — Python kernel + planned TS Web SPA only.
6. **Live optional** — kernel must boot and pass tests with Live disabled.
7. **Real-money safety** — order paths require RiskGate + idempotency + explicit failure modes.

---

## 7. Dependency Rules

```text
interface/  ──▶  runtime/  ──▶  application/  ──▶  domain/
                    │              ▲
                    └──▶  infrastructure/ ──┘
                    └──▶  brokers/ (plugins)
                    └──▶  datalake/
```

| Layer | May import | Must NOT import |
|---|---|---|
| `domain` | stdlib, self | application, infrastructure, runtime, brokers, interface |
| `application` | domain | infrastructure, runtime, brokers, interface |
| `infrastructure` | domain | runtime, interface, application |
| `runtime` | application, infrastructure, domain, brokers, datalake | — (composition root) |
| `interface` | application, runtime (for DI) | brokers directly |
| `brokers` | domain ports | application internals, OMS concretes |

Enforced by import-linter contracts in `pyproject.toml` (CI-blocking).

---

## 8. Layering Rules

| Layer | Owns | Must NOT own |
|---|---|---|
| **Domain** | Entities, VOs, FSMs, ports (Protocols), domain events | HTTP, DB drivers, broker SDKs |
| **Application** | Use cases: OMS, execution, trading orchestration, risk orchestration | Concrete infra, broker wire format |
| **Infrastructure** | EventBus impl, caches, auth, persistence adapters, resilience | Business rules, strategy logic |
| **Runtime** | Factory, wiring, plugin discovery, capability selection | Domain entities |
| **Brokers** | Wire protocol, auth, broker-specific mapping | Risk authority, OMS state |
| **Interface** | HTTP/CLI/TUI handlers, request/response schemas | Business rules |
| **Datalake** | Ingestion, storage, quality, research queries | Order placement |

---

## 9. Extension Philosophy

### Plugin entry-points

| Group | Provides | Registered in |
|---|---|---|
| `tradex.brokers` | `(broker_id, BrokerAdapter)` | `pyproject.toml` |
| `tradex.exchanges` | `(exchange_id, ExchangeAdapter, TradingCalendar)` | `pyproject.toml` |
| Execution targets | Wired at composition root (not entry-point yet; see `04-component-contracts.md`) | `runtime/factory.py` |

### Extension rules

1. Plugins implement **domain ports**, never reach into application concretes.
2. New execution target = new `ExecutionTarget` impl + factory registration; **no** strategy/risk/OMS fork.
3. New strategy = plugin or registered class; consumes indicators via pipeline ports.
4. Feature flags for **product surfacing**, not for architectural forks.
5. Every extension ships with at least one integration test through real wiring.

---

## Invariant Index (for cross-reference)

Cite as `P1`–`P12` in gap analysis, ADRs, and code review. Scenario IDs cite `01a` as `QA-<attribute>-<n>`.
