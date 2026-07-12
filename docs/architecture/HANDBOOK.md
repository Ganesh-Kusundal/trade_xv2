# Trade_XV2 Trading OS — Architecture Handbook

**Version:** 1.0  
**Status:** Phase 1 — Architecture Foundation (TRANS-P1-001) ✅  
**Owner:** Domain & Contracts / Chief Architect

---

## 1. Vision

Trade_XV2 is an **institutional-grade Trading Operating System** for Indian exchanges: broker-agnostic, event-driven, and continuously deployable. Product code interacts through **stable contracts** (SDK, commands, events, ports)—never through broker wire details or ad-hoc scripts.

### Non-goals

- Big-bang package renames or monolithic `Runtime` god-object
- Supporting Zerodha (see ADR-013)
- Claiming live parity from paper-only certification
- Speculative abstractions without a strangler removal condition

---

## 2. Architecture principles

1. **Architecture before implementation** — ADR + contract before code move
2. **Business capabilities before modules** — own by bounded context
3. **Stable contracts before implementations** — ports and event schemas versioned
4. **Evolutionary refactoring** — shims with explicit removal conditions
5. **Fail closed** — empty, stale, UNKNOWN, and unavailable are distinct loud states
6. **Single execution spine** — ledger + projections; modes differ only at I/O
7. **Plugin brokers** — add broker = entry point + wire + certification
8. **Three equivalent surfaces** — SDK, CLI, MCP share `brokers.services` core (ADR-014)

---

## 3. Bounded contexts

| Context | Owns | Must not own |
|---------|------|--------------|
| **Domain** | Aggregates, VOs, events, ports | Broker wire, UI, persistence impl |
| **Market Data** | Feeds, normalization, subscriptions | Order placement |
| **Decision / Research** | Scanners, strategies, signals | OMS mutation, broker I/O |
| **Execution / OMS** | Order lifecycle, risk, fill ingress | Broker auth details |
| **Portfolio** | Positions, PnL projections from ledger | Broker truth |
| **Broker Integration** | Wire adapters, auth, capabilities | Domain order truth |
| **Reconciliation** | Drift detection, repair commands | Strategy state |
| **Operations** | Lifecycle, certification, readiness | Trading rules |
| **Presentation** | API, CLI, TUI, MCP transport | Hidden order placement |

See [bounded-contexts design](../reviews/2026-07-10-trading-platform-review/design/bounded-contexts-and-ownership.md), [ARCHITECTURE-ARTIFACTS.md](../reviews/2026-07-11-trading-os-transformation-program/ARCHITECTURE-ARTIFACTS.md), [FLOWS.md](./FLOWS.md), and [DEPENDENCY_GRAPH.md](./DEPENDENCY_GRAPH.md).

---

## 4. Runtime kernel (composition)

Two **documented** composition paths today (target: unify via `runtime.factory.build` — ADR-017):

1. **SDK:** `tradex.open_session()` → gateway + CQRS dispatchers
2. **Service:** `TradingRuntimeFactory.build_from_broker_service()`

Canonical modules: see [RUNTIME_KERNEL.md](./RUNTIME_KERNEL.md).

**Process invariant:** one `TradingContext` per process via `application.oms.process_context` — duplicate registration is a defect.

---

## 5. Package structure

Single root: `src/`. Layers enforced by import-linter (**15/15 contracts pass**).
Details: [DEPENDENCY_RULES.md](./DEPENDENCY_RULES.md). Engineering rules: [STANDARDS.md](../engineering/STANDARDS.md).

```
domain → (nothing outer)
application → domain, ports
infrastructure → domain
brokers → domain
runtime → application, infrastructure, brokers
tradex → runtime (thin SDK)
interface → runtime, application (no broker internals)
analytics → domain (D2: no OMS)
```

---

## 6. Aggregates (summary)

| Aggregate | Key invariants |
|-----------|----------------|
| **Order** | Legal status transitions; UNKNOWN blocks retry until recon |
| **Execution** | Fill idempotency; publishes `TRADE_APPLIED` |
| **Position** | Updated only from fills; PnL math with multiplier |
| **Subscription** | active/degraded/ended; degraded ≠ silent |
| **BrokerSession** | authenticated → trading_enabled with readiness evidence |

Full spec: [OBJECT_MODEL.md](./OBJECT_MODEL.md).

---

## 7. Event model (summary)

- **Commands** at boundary: `PlaceOrder`, `CancelOrder`, `StartSubscription`, …
- **Domain events** are facts with envelope metadata (TRANS-P5-034)
- **Integration DTOs** at broker boundary only — no raw dicts in domain

Catalog: [EVENT_CATALOG.md](./EVENT_CATALOG.md). Glossary: [GLOSSARY.md](./GLOSSARY.md).

---

## 8. Broker plugin contract

Per ADR-014:

- Public: `BrokerSession` + domain `Instrument`
- Wire: `brokers.<name>.wire.*WireAdapter`
- Register: `pyproject.toml` `tradex.brokers` + `register_broker_plugin()`
- Certify: `broker verify` / `broker certify` before production

**SegmentMapperRegistry:** brokers register mappers at plugin import;
`domain.market.segment_registry.segment_mapper_for` fails closed if plugin
not loaded. See [DEPENDENCY_RULES.md](./DEPENDENCY_RULES.md).

---

## 9. Developer platform

Operators and agents validate via:

```bash
broker --broker paper doctor
broker --broker paper verify
broker --broker paper certify --json
```

Not ad-hoc `scripts/verify/*` in CI (guarded by `test_workflow_paths.py`).

---

## 10. Architecture review checklist (PR)

- [ ] Bounded context identified
- [ ] No new `domain → brokers` imports
- [ ] No new `application → infrastructure` imports (except approved)
- [ ] `lint-imports` passes
- [ ] `tests/architecture` passes
- [ ] Flow/ADR updated if behavior changed
- [ ] Deployable with safe feature-flag default

---

## References

- [Transformation program](../reviews/2026-07-11-trading-os-transformation-program/README.md)
- [Architecture audit](../reviews/2026-07-11-trading-os-architecture-audit/README.md)
- ADR-012 CQRS, ADR-013 Brokers, ADR-014 Persistence, ADR-014-brokers Trading OS