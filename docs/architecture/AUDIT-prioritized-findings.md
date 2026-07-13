# Prioritized Architecture Audit — TradeXV2 / TradeX Trading OS

> Companion to `AUDIT-current-state.md`. Findings are prioritized by **severity × blast radius ×
> fixability**. Every item has verified `file:line` evidence. **No code has been modified.**
> Severity: 🔴 blocker/real-money risk · ⚠️ significant · 🟡 moderate/cleanup.

---

## 0. Priority Legend

- **P0** — correctness/safety or trust-eroding; fix before any further feature work.
- **P1** — structural debt that compounds; schedule next.
- **P2** — cleanup; safe to batch.

---

## 1. Prioritized Findings Table

| # | ID | Finding | Sev | Layer | Evidence |
|---|---|---|---|---|---|
| 1 | SM-01 | Linter-invisible dynamic broker imports in `infrastructure` (violates "infrastructure independence") | 🔴 | infra | `infrastructure/gateway/factory.py:393,420,443` (`importlib.import_module("brokers.dhan…")`) |
| 2 | SM-02 | `infrastructure/broker_plugin.py` resolves brokers by **string** capability module path | 🔴 | infra | `infrastructure/broker_plugin.py:93,105` (`"brokers.dhan.config.capabilities"`) |
| 3 | SM-03 | `runtime ↔ interface` circular dependency via `api_bootstrap` shim | 🔴 | runtime/interface | `runtime/api_bootstrap.py:9` ↔ `interface/api/bootstrap.py:14` |
| 4 | SM-04 | 152 private `getattr` reach-throughs breach encapsulation (incl. on reconcile/risk paths) | ⚠️ | app/interface/infra | `oms/reconciliation_service.py:178-182`, `order_placer.py:75`, `interface/api/deps.py:333` |
| 5 | SM-05 | 3 parallel idempotency implementations | ⚠️ | infra/brokers/app | `infrastructure/idempotency/service.py:61`, `brokers/common/idempotency.py:54`, `application/oms/idempotency_guard.py:19` |
| 6 | SM-06 | Duplicate domain models inside broker packages | ⚠️ | brokers/domain | `brokers/dhan/domain.py:44,56,69,128` vs `domain/market_enums.py:11,28`, `domain/entities/instrument_record.py:21` |
| 7 | SM-07 | 2 live config systems (`AppConfig` vs `SettingsLoaderBase`) | ⚠️ | config/infra | `config/schema.py:22` vs `infrastructure/config/settings.py:46` |
| 8 | SM-08 | God objects exempted from size gate (20 exceptions; 4 exceed 650 raw LOC) | ⚠️ | multiple | `analytics/replay/engine.py:826`, `brokers/dhan/data/depth_feed_base.py:722`, `application/oms/context.py:688`, `interface/api/schemas.py:678` |
| 9 | SM-09 | `application → infrastructure` inversion tolerated by `ignore_imports` (not true layering) | ⚠️ | app/infra | `application/services/provenance.py:19`, `download_engine.py:42`, `historical_data.py:7`, `data/historical_coordinator.py:77` |
| 10 | SM-10 | String-based `broker_id` routing (no enum, typo-unsafe) | ⚠️ | runtime/brokers | `runtime/broker_infrastructure.py:66` (`BrokerInfrastructure.gateway_for(broker_id: str)`) |
| 11 | SM-11 | 26 of 38 `ignore_imports` are dead ("No matches") — config rot masks nothing | 🟡 | tooling | `pyproject.toml` contracts (e.g. `runtime.broker_infrastructure → brokers.dhan.config.capabilities`) |
| 12 | SM-12 | Dual CLI (`tradex` + `broker`) violates single-CLI target | 🟡 | interface | `pyproject.toml:33-34` |
| 13 | SM-13 | Dead `broker-mcp` entry-point + docs reference non-existent MCP servers | 🟡 | tooling/docs | `src/tradexv2.egg-info/entry_points.txt`; `scripts/verify/test_mcp_integration.py:13` |
| 14 | SM-14 | 174 builtin `print()` instead of logging | 🟡 | multiple | `analytics/backtest/run_backtest.py:71`, `config/validator.py:16` |
| 15 | SM-15 | 39 `import *` star imports (namespace opacity) | 🟡 | multiple | `brokers/services/core.py:25-31`, `infrastructure/auth/__init__.py:2-10` |
| 16 | SM-16 | 34 `global` statements | 🟡 | multiple | `interface/api/deps.py:48,80`, `runtime/event_loop.py:54` |
| 17 | SM-17 | 10 exceptions outside `TradeXV2Error` taxonomy | 🟡 | domain/infra | `infrastructure/security/webhook_auth.py:11`, `domain/errors.py:114,154` |
| 18 | SM-18 | Intra-broker duplicated connection/order/gateway logic not lifted to `brokers/common` | 🟡 | brokers | `brokers/dhan/streaming/connection.py:70` vs `websocket/connection.py:30`; `dhan/execution/orders.py:64` vs `upstox/adapters/order_gateway.py:29` |
| 19 | SM-19 | `MultiStrategyRuntime` builds a pipeline never wired to the orchestrator (dead divergence) | 🟡 | app | `application/trading/multi_strategy_runtime.py:15` |
| 20 | SM-20 | `tradex` SDK leaks into `domain` internals | 🟡 | tradex/domain | `src/tradex/__init__.py:43-56` |

---

## 2. Category Deep-Dives

### 2.1 Layering & Coupling (highest risk)
- **SM-01/02** are the most dangerous: they are **real layer violations the import-linter cannot see**
  because they use `importlib.import_module` / string module paths. The green build is therefore
  *partially illusory* for `infrastructure → brokers`. These must be routed through the
  `runtime` composition root (which already is the sanctioned broker importer) or a true plugin
  registry, so the dependency is explicit and lintable.
- **SM-03** (`runtime ↔ interface` cycle) is mediated by a shim today but is a genuine package cycle;
  `interface/api/bootstrap.py:14` importing `runtime.trading_runtime_factory` while `runtime/
  api_bootstrap.py:9` imports `interface.api.bootstrap`. Resolve by having the API bootstrap call the
  runtime factory only (one direction).
- **SM-09**: `application` importing `infrastructure` is explicitly sanctioned by `ignore_imports`, but
  it is still an inversion of the documented rule (application may not import infrastructure). The
  exceptions should be driven to zero by promoting the needed capabilities (audit, clock, parquet IO)
  to `domain` ports or `runtime` wiring.
- **SM-11**: 26 dead `ignore_imports` lines reduce the contract's signal-to-noise; prune them so a
  future real violation isn't hidden among stale exceptions.

### 2.2 Duplication
- **SM-05** (3 idempotency stacks) and **SM-07** (2 config systems) are the clearest "duplicate
  cross-cutting infra" smells. Pick one idempotency (`infrastructure/idempotency`) and one config
  (`AppConfig`); delete/adapt the rest.
- **SM-06** (broker-local domain types) is a domain-integrity risk: the import bans in `pyproject.toml`
  (lines 287-290) exist *because* `brokers.dhan.domain` redefined `Quote/Balance/DepthLevel/
  MarketDepth`. Any code importing from the broker package instead of `domain` is using a divergent
  model.
- **SM-18** (intra-broker duplication) is normal for adapter code but Dhan has two near-identical
  reconnecting-connection classes that should collapse to one `brokers/common` base.

### 2.3 Encapsulation & Safety
- **SM-04** (152 private `getattr` reach-throughs): the most pervasive smell. G7's *risk-manager*
  reach-through is gone, but reconciliation (`reconciliation_service.py:178-182` reaching into
  `_lifecycle`/`_trade_recorder`) and sizing (`order_placer.py:75` reaching into `_capital_provider`)
  still violate encapsulation and will break silently on refactor. Replace with explicit accessors or
  ports.
- **SM-10** (string `broker_id`) is a latent correctness bug — a typo'd broker id fails at runtime, not
  at import; an enum (`BrokerId`, already present per progress-tracker M7) should be the routing key.

### 2.4 Quality Hygiene
- **SM-08** god objects: the size gate exists and runs in CI, but 20 exemptions mean the "hard limit" is
  advisory. Drive exemptions to zero by decomposing the listed files.
- **SM-12/13/14/15/16/17/20**: standard hygiene — single CLI, remove dead MCP entry-point, route
  prints to logging, eliminate star imports and `global`s, fold stray exceptions into `TradeXV2Error`,
  decouple `tradex` from `domain` internals.

---

## 3. What Is NOT a Problem (do not "fix")

- Domain purity — confirmed clean; do not add domain→inward imports.
- import-linter being green overall — keep it the gate; the issue is *hidden* dynamic imports, not the
  contract itself.
- MCP consolidation — already done (0 servers); the work is deleting dead references, not building.
- G7 kill-switch — closed.
- Reconciliation on hot path — done (wired to `TRADE_APPLIED`/`ORDER_UPDATED`).
- Repo-root ad-hoc scripts — already cleaned (G8 effectively done).

---

## 4. Recommended Fix Order (summary; full plan in `AUDIT-target-state-and-plan.md`)

1. **P0:** SM-01, SM-02, SM-03 — make `infrastructure→brokers` and `runtime↔interface` explicit &
   lintable. (Small, high-value, restores trust in the green build.)
2. **P1:** SM-04, SM-05, SM-06, SM-07, SM-09, SM-10 — close encapsulation + dedupe infra + enum routing.
3. **P2:** SM-08, SM-11, SM-12…SM-20 — hygiene, dead-config prune, god-object decomposition.
