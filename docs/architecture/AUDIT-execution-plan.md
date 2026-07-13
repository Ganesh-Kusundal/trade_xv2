# Execution Plan — Handling All Findings (Design · Architecture · Cleanup)

> Consolidated, actionable plan for **all 20 audit findings** (SM-01…SM-20). Maps every finding to a
> **design decision**, an **architectural change**, and a **cleanup action**, sequenced into 5 phases.
> Companion to `AUDIT-current-state.md`, `AUDIT-prioritized-findings.md`,
> `AUDIT-target-state-and-plan.md`. **No code modified.** Each phase is independently releasable and
> must keep `import-linter` + architecture tests green.

---

## 1. Governing Principles

**Design level**
- Dependencies are **explicit and statically visible** — no `importlib`/string-module resolution.
- Brokers are selected **once at startup** by `BrokerId` enum via a plugin registry; never by string.
- State crosses boundaries only through **ports / explicit accessors** — never `getattr(., "_x")`.
- One implementation per cross-cutting concern (event bus, idempotency, config, risk gate).

**Architecture level**
- `import-linter` contract is the single source of truth for layering; it must stay green.
- `domain` is pure; `application` depends only on domain ports; `infrastructure` depends only on
  domain ports; `runtime` is the ONLY concrete-broker importer; `interface` never imports `brokers`.
- The green build is trustworthy **only if** no linter-invisible dynamic imports exist.

**Cleanup level**
- Delete dead code/config, dead entry-points, stray `print()`, star imports, `global`s, and
  out-of-taxonomy exceptions. Drive the file-size exemption list to zero.

---

## 2. Master Finding → Treatment Matrix

| ID | Sev | Phase | Design decision | Architectural change | Cleanup action |
|---|---|---|---|---|---|
| SM-01 | 🔴 | 0 | Broker construction lives only in `runtime` composition root | `infrastructure` may not `importlib` brokers → inject gateways from `runtime.broker_accessors` | Delete dynamic `import_module("brokers.*")` in `gateway/factory.py:393,420,443` |
| SM-02 | 🔴 | 0 | Broker capabilities resolved by `BrokerId` enum, not string path | `infrastructure/broker_plugin.py` takes a resolved object, not `"brokers.dhan.config.capabilities"` | Replace string paths (`:93,105`) with registry lookup |
| SM-03 | 🔴 | 0 | API bootstrap depends *down* on runtime only | Break cycle: `interface/api/bootstrap.py:14` → `runtime` only; drop `runtime/api_bootstrap.py:9` | Delete `runtime/api_bootstrap.py` shim |
| SM-04 | ⚠️ | 1 | State accessed via ports/accessors, not private attrs | Add `OrderManager`/`TradingContext` accessors; inject `_capital_provider` as port | Replace 152 `getattr(., "_x")`; CI grep-gate bans them |
| SM-05 | ⚠️ | 1 | Single idempotency service | Canonical = `infrastructure/idempotency`; others delegate/delete | Delete `brokers/common/idempotency.py:54`, `application/oms/idempotency_guard.py:19` |
| SM-06 | ⚠️ | 1 | Domain is the only model | Broker packages import `domain` types; bans in `pyproject` stay | Delete `brokers/dhan/domain.py:44,56,69,128` redefinitions |
| SM-07 | ⚠️ | 1 | Single config = `AppConfig` | `SettingsLoaderBase` deprecated behind `AppConfig` | Delete `infrastructure/config/settings.py:46` + broker `SettingsLoader`s |
| SM-08 | ⚠️ | 3 | Files ≤650 LOC (hard) | Promote decomposition; shrink exemption list | Decompose `replay/engine.py:826`, `depth_feed_base.py:722`, `oms/context.py:688`, `api/schemas.py:678` |
| SM-09 | ⚠️ | 2 | `application` depends only on `domain` ports | Promote audit/clock/parquet-IO/historical to ports or `runtime` wiring | Drive `application→infrastructure` `ignore_imports` to zero |
| SM-10 | ⚠️ | 1 | Routing keyed by `BrokerId` enum | `BrokerInfrastructure.gateway_for(BrokerId)` | Replace `str` param (`broker_infrastructure.py:66`) |
| SM-11 | 🟡 | 2 | Contract signal is clean | Prune dead `ignore_imports` | Remove 26 "No matches" exception lines in `pyproject.toml` |
| SM-12 | 🟡 | 4 | One CLI = `tradex` | `tradex` subsumes `broker` commands | Delete `broker = brokers.cli.broker` entry (`pyproject.toml:33`) |
| SM-13 | 🟡 | 4 | No phantom surfaces | Remove dead MCP references | Delete `broker-mcp` entry-point; fix `test_mcp_integration.py:13` + docs |
| SM-14 | 🟡 | 4 | Logging, not printing | Route to `logging`/`rich` log | Replace 174 builtin `print()` |
| SM-15 | 🟡 | 4 | Explicit namespaces | Replace star imports with explicit names | Fix 39 `import *` (`brokers/services/core.py:25-31` etc.) |
| SM-16 | 🟡 | 4 | No module-level mutable globals | Use DI / context objects | Remove 34 `global` (`interface/api/deps.py:48` etc.) |
| SM-17 | 🟡 | 4 | One exception taxonomy | All errors extend `TradeXV2Error` | Fold 10 stray bases (`webhook_auth.py:11` etc.) |
| SM-18 | 🟡 | 4 | Shared adapter base in `brokers/common` | Lift duplicated connection/order/gateway logic | Collapse Dhan duplicate connections; unify order gateways |
| SM-19 | 🟡 | 4 | No dead divergence | `MultiStrategyRuntime` wires to orchestrator or is deleted | Resolve `multi_strategy_runtime.py:15` |
| SM-20 | 🟡 | 4 | SDK decoupled from `domain` internals | `tradex` imports via public surface | Fix `tradex/__init__.py:43-56` |

---

## 3. Phased Plan

### Phase 0 — Restore trust in the green build (P0: SM-01, SM-02, SM-03)
**Objective:** make every layer dependency explicit and lintable.
**Design:** broker construction + capability resolution happen only in `runtime` via a `BrokerId`-
keyed registry; API bootstrap depends downward only.
**Architectural changes:**
- Inject gateways built by `runtime.broker_accessors` into `infrastructure.gateway.factory` (no
  `importlib` of `brokers.*`).
- `infrastructure/broker_plugin` receives resolved capability objects, not string module paths.
- `interface/api/bootstrap.py` calls `runtime.trading_runtime_factory` only; delete `runtime/api_bootstrap.py`.
**Cleanup:** delete dynamic imports, the `api_bootstrap` shim.
**Add CI gate:** import-linter contract forbidding `importlib`/`__import__` of `brokers.*` outside `runtime`.
**Acceptance:** no `importlib`/string broker resolution outside `runtime`; `runtime↔interface` no
longer a cycle (verify with `graphify path`); import-linter green.

### Phase 1 — Encapsulation & dedupe cross-cutting infra (P1: SM-04, SM-05, SM-06, SM-07, SM-10)
**Objective:** close encapsulation breaches; one idempotency, one config, one model, typed routing.
**Design:** explicit accessors/ports replace private reach-throughs; `BrokerId` enum is the sole
routing key; `domain` is the only model; `AppConfig` is the only config.
**Architectural changes:**
- Add `OrderManager`/`TradingContext` accessors; inject capital provider as a port; remove the 5
  hot-path `getattr` reach-throughs.
- Collapse 3 idempotency stacks → `infrastructure/idempotency` canonical.
- Delete broker-local domain redefinitions (`brokers/dhan/domain.py`); rely on `pyproject` bans.
- Deprecate `SettingsLoaderBase` behind `AppConfig` (ADR-003); broker settings load via `AppConfig`.
- `BrokerInfrastructure.gateway_for(BrokerId)`.
**Cleanup:** delete `brokers/common/idempotency.py`, `application/oms/idempotency_guard.py`,
`infrastructure/config/settings.py`, broker `SettingsLoader`s, `brokers/dhan/domain.py` redefinitions.
**Add CI gate:** grep-gate banning `getattr(., "_` in `src/`.
**Acceptance:** 0 hot-path reach-throughs; 1 idempotency; 1 config; 0 broker-local domain types;
`BrokerId` enum routing; architecture + integration tests green.

### Phase 2 — Tighten the contract (P1→P2: SM-09, SM-11)
**Objective:** remove tolerated inversions and dead config so future violations can't hide.
**Design:** `application` depends only on `domain` ports; contract list is minimal and meaningful.
**Architectural changes:** promote audit/clock/parquet-IO/historical-data to `domain` ports or
`runtime` wiring so `application→infrastructure` `ignore_imports` reach zero.
**Cleanup:** prune the 26 dead `ignore_imports` lines in `pyproject.toml`.
**Acceptance:** import-linter green with **no** `application→infrastructure` and **no** dead ignores.

### Phase 3 — God-object decomposition (P2: SM-08)
**Objective:** enforce the file-size hard limit for real.
**Design:** files ≤650 LOC (hard), ≤400 (soft); every exemption has owner + due-date; no new
exemption without one.
**Architectural changes:** decompose `analytics/replay/engine.py`, `brokers/dhan/data/depth_feed_base.py`,
`application/oms/context.py`, `interface/api/schemas.py` into focused modules.
**Cleanup:** decrement the 20-entry exemption list in `tests/architecture/test_file_size_limit.py`
toward zero.
**Acceptance:** exemption list shrinks each milestone; no new file >400 LOC slips through.

### Phase 4 — Surface & hygiene consolidation (P2: SM-12…SM-20)
**Objective:** one surface per kind; clean hygiene.
**Design:** single CLI (`tradex`); no phantom MCP; logging/structured namespaces; one exception
taxonomy; SDK decoupled; shared broker bases.
**Architectural changes:** `tradex` subsumes `broker` CLI; `tradex` imports `domain` via public
surface; `MultiStrategyRuntime` wired or deleted; duplicated Dhan/Upstox adapter logic lifted to
`brokers/common`.
**Cleanup:** delete `broker` CLI entry + dead `broker-mcp` entry-point + MCP docs/test refs; replace
174 `print()`, 39 `import *`, 34 `global`; fold 10 stray exceptions into `TradeXV2Error`.
**Acceptance:** single CLI; 0 `print()`/star-import/`global` in `src/`; all exceptions extend
`TradeXV2Error`; `tradex` decoupled from `domain` internals.

---

## 4. Cross-Cutting CI Guardrails to Add

1. **No dynamic broker import** — import-linter/static check forbidding `importlib(__import__)` of
   `brokers.*` outside `runtime`.
2. **No private reach-through** — pre-commit/CI grep-gate: `getattr\(\s*\w+,\s*["']_` fails.
3. **Single config / idempotency** — architecture test asserting exactly one canonical implementation.
4. **File-size gate** — keep `test_file_size_limit.py`; forbid new exemptions without owner+due-date.
5. **Single CLI** — architecture test asserting one console script (`tradex`) in `pyproject`.

---

## 5. Sequencing & Dependencies

```
Phase 0 (SM-01,02,03)  ──▶  Phase 1 (SM-04,05,06,07,10)  ──▶  Phase 2 (SM-09,11)
                                                                      │
                                                      Phase 3 (SM-08)  ─┐
                                                                      ├──▶  Phase 4 (SM-12..20)
Phase 0 must land first: until `infrastructure→brokers` and `runtime↔interface` are explicit,
the green build is partially illusory and later metrics are untrustworthy. Phases 3 & 4 can run
in parallel after Phase 2, gated by the same import-linter + test suite.
```

---

## 6. Effort & Risk Notes
- **Phase 0:** S–M, low risk, highest trust payoff. Do first.
- **Phase 1:** M, medium risk (cutover shims for config/idempotency need parity tests — zero-parity rule).
- **Phase 2:** M, low risk (mechanical promotion to ports).
- **Phase 3:** M–L, churn risk (decompose god objects behind stable interfaces).
- **Phase 4:** S–M, low risk (hygiene + surface consolidation).

Every phase ships behind the existing 7,629-test suite + architecture tests; import-linter stays green.
