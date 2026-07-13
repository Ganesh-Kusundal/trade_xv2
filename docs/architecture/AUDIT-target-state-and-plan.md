# Target-State Architecture & Incremental Migration Plan — TradeXV2

> Companion to `AUDIT-current-state.md` and `AUDIT-prioritized-findings.md`. **No code has been
> modified.** This defines the target and a step-by-step migration that keeps the app deployable and
> import-linter green after every step. Tie-in to existing ADRs: ADR-002 (layer rule), ADR-003 (single
> config), ADR-004 (single event bus), ADR-005 (exchange-agnostic datalake), ADR-006 (risk gate).
> Corrections vs `roadmap.md`/`REVIEW.md`: MCP is already gone (don't build it); G7/G8 largely done;
> import-linter is green (the risk is *hidden* dynamic imports, not the contract).

---

## 1. Target-State Principles

1. **The import-linter contract is the single source of truth for layering** — keep it green; any new
   broker/infra dependency must be *visible* to grimp (no `importlib`/string-module tricks).
2. **`runtime` is the ONLY concrete-broker importer**, and it does so through a **typed plugin
   registry keyed by `BrokerId` enum** — never string module paths.
3. **One of each cross-cutting service:** one event bus, one idempotency, one config (`AppConfig`),
   one risk gate port. Duplicates are deleted, not wrapped.
4. **Domain is the only model.** Broker packages reference `domain` types; they never redefine
   `Quote/Order/Position/…`.
5. **One external surface per kind:** one CLI (`tradex`), one SDK (`tradex`), one API, one TUI. MCP is
   optional and, if added, a single facade.
6. **Encapsulation is enforced:** zero `getattr(obj, "_private")` reach-throughs; state accessed via
   ports/accessors.

---

## 2. Target Package Skeleton (evolutionary)

```
src/domain/            pure core (entities, ports, events, value objects) — unchanged
src/application/       use-cases; depends ONLY on domain ports
src/infrastructure/    adapters; depends on domain ports ONLY (no broker imports, ever)
src/runtime/           composition root; ONLY concrete-broker importer, via BrokerRegistry[BrokerId]
src/brokers/          → re-home as plugins (tradex.brokers entry-point); no domain redefinitions
src/interface/        api (FastAPI) + ui (TUI) over the tradex SDK; never imports brokers
src/config/           single AppConfig schema; SettingsLoaderBase deleted
src/datalake/         exchange-agnostic (reads conventions via ExchangeAdapter plugin)
src/analytics/        strategy/backtest/replay (no interface imports)
src/tradex/           public SDK; imports domain only via its public surface
```

---

## 3. Incremental Migration Plan

Each phase is **independently releasable**, keeps import-linter green, and ships with/extends an
integration test. Stop-and-verify after each.

### Phase 0 — Restore trust in the green build (P0)
**Goal:** eliminate linter-invisible layer violations.
- **T0-1 (SM-01):** Replace `importlib.import_module("brokers.dhan…")` in
  `infrastructure/gateway/factory.py:393,420,443` with a call into `runtime.broker_accessors`
  (composition root) or a `BrokerRegistry` resolved at startup. Add an import-linter contract
  forbidding `importlib` broker resolution outside `runtime`.
- **T0-2 (SM-02):** Replace string capability-module paths in `infrastructure/broker_plugin.py:93,105`
  with `BrokerId`-keyed lookups resolved by `runtime`.
- **T0-3 (SM-03):** Break the `runtime ↔ interface` cycle — make `interface/api/bootstrap.py:14`
  call `runtime.trading_runtime_factory` *only*; delete the `runtime.api_bootstrap` shim
  (`api_bootstrap.py:9`).
- **Acceptance:** import-linter green with **no `importlib`/string broker resolution outside
  `runtime`**; `runtime ↔ interface` no longer a cycle (verify with graphify path).

### Phase 1 — Encapsulation & dedupe cross-cutting infra (P1)
- **T1-1 (SM-04):** Replace the 5 `order_manager`/`context` private reach-throughs
  (`reconciliation_service.py:178-182`, `order_placer.py:75`, `interface/api/deps.py:333`,
  `tradex/session.py:369,381`, `domain/session.py:131`, `paper_gateway.py:53`) with explicit
  accessors/ports. Add a CI grep-gate banning `getattr(., "_`)`.
- **T1-2 (SM-05):** Collapse 3 idempotency stacks → `infrastructure/idempotency` is canonical;
  `brokers/common/idempotency.py` and `application/oms/idempotency_guard.py` delegate/delete.
- **T1-3 (SM-07):** Deprecate `SettingsLoaderBase` (`infrastructure/config/settings.py:46`) behind
  `AppConfig`; route `DhanSettingsLoader`/`UpstoxSettingsLoader` through `AppConfig` (ADR-003).
- **T1-4 (SM-06):** Delete broker-local domain redefinitions (`brokers/dhan/domain.py:44,56,69,128`);
  import `domain/market_enums.py`, `domain/entities/instrument_record.py`. Keep the `pyproject` bans.
- **T1-5 (SM-10):** Route `BrokerInfrastructure.gateway_for` (`broker_infrastructure.py:66`) by
  `BrokerId` enum, not `str`.
- **Acceptance:** 0 private reach-throughs on hot paths; 1 idempotency; 1 config; 0 broker-local
  domain types; `BrokerId` enum everywhere for routing.

### Phase 2 — True layering & dead-config prune (P1→P2)
- **T2-1 (SM-09):** Drive `application → infrastructure` `ignore_imports` to zero by promoting
  (audit, clock, parquet IO, historical_data) to `domain` ports or `runtime` wiring.
- **T2-2 (SM-11):** Prune the 26 dead `ignore_imports` lines so the contract's signal is clean.
- **Acceptance:** import-linter green with no application→infrastructure and no dead ignores.

### Phase 3 — God-object decomposition (P2)
- **T3-1 (SM-08):** Decompose the 4 >650-LOC files and decrement the 20-entry exemption list in
  `tests/architecture/test_file_size_limit.py` toward zero (keep the gate; forbid new exemptions
  without owner + due-date).
- **Acceptance:** exemption list shrinks each milestone; no new file >400 LOC.

### Phase 4 — Surface & hygiene consolidation (P2)
- **T4-1 (SM-12):** Consolidate the `broker` CLI into `tradex` (single CLI target).
- **T4-2 (SM-13):** Remove dead `broker-mcp` entry-point + fix `scripts/verify/test_mcp_integration.py`
  / docs referencing non-existent MCP servers.
- **T4-3 (SM-14/15/16):** Route 174 `print()` to logging; eliminate 39 `import *`; remove 34 `global`.
- **T4-4 (SM-17):** Fold the 10 out-of-taxonomy exceptions into `TradeXV2Error`.
- **T4-5 (SM-18):** Lift duplicated Dhan connection/order/gateway logic into `brokers/common`.
- **T4-6 (SM-19):** Either wire `MultiStrategyRuntime` to the orchestrator or delete it.
- **T4-7 (SM-20):** Decouple `tradex` SDK from `domain` internals (import via public surface).

---

## 4. Sequencing Rationale

- **Phase 0 first** because the green import-linter build is currently *partially illusory*; until
  `infrastructure→brokers` and `runtime↔interface` are explicit and lintable, no later metric can be
  trusted.
- **Phase 1** delivers the real-money-safety and duplication wins (encapsulation, single idempotency/
  config, typed routing) with small, safe diffs.
- **Phase 2** tightens the contract so future violations are impossible to hide.
- **Phases 3–4** are mechanical hygiene that can run continuously without risk.

## 5. Risks & Guardrails
- **Guardrail:** import-linter + architecture tests must stay green after every task (they are the
  contract). Add a new contract forbidding `importlib` broker resolution outside `runtime`.
- **Guardrail:** add a CI grep-gate for `getattr(., "_` to prevent regression of SM-04.
- **Risk:** deleting `SettingsLoaderBase`/`idempotency` duplicates needs a deprecation shim + parity
  test during cutover (zero-parity rule).
- **Risk:** routing-by-enum changes call sites — cover with the existing integration suite + a new
  architecture test asserting `BrokerId` is the only routing key.

## 6. Success Criteria (target)
- import-linter green; **no `importlib`/string broker resolution outside `runtime`**; no
  `runtime↔interface` cycle.
- 0 private `getattr` reach-throughs; 1 event bus, 1 idempotency, 1 config, 1 risk-gate port.
- 0 broker-local domain type redefinitions; `BrokerId` enum is the sole routing key.
- Single CLI (`tradex`); dead MCP references gone; `tradex` decoupled from `domain` internals.
- File-size exemption list trending to zero; no new file >400 LOC.
- 7,629-test suite + architecture tests green after each phase.
