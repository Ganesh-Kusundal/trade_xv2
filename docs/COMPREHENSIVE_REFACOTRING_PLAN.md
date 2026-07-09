# TradeXV2 — Comprehensive Structural Cleanup & Architectural Reorganization

> **Version:** 3.0 (validated)  
> **Branch:** `refactor/structural-cleanup`  
> **Checkpoint:** `ee8fe75`  
> **Date:** 2026-07-10  
> **Principles:** Clean Architecture (Robert C. Martin), SOLID, YAGNI, DRY, Agile Incrementalism (Venkat Subramaniam)  
> **Grounded in:** Every finding traced to a specific file, line count, class, and import.  
> **Validated by:** Multi-agent deep audit of 1,100+ source files, 642 test files, 227 `__pycache__` dirs.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Validated Findings Index](#2-validated-findings-index)
3. [Repository Inventory](#3-repository-inventory)
4. [Architecture Root Cause Analysis](#4-architecture-root-cause-analysis)
5. [Clean Architecture Target State](#5-clean-architecture-target-state)
6. [Phased Execution Plan (10 Phases)](#6-phased-execution-plan)
7. [Dependency Graph](#7-dependency-graph)
8. [Multi-Agent Team Execution Model](#8-multi-agent-team-execution-model)
9. [Regression Gate Protocol](#9-regression-gate-protocol)
10. [Risk Mitigation & Rollback](#10-risk-mitigation--rollback)
11. [Appendices](#11-appendices)

---

## 1. Executive Summary

### What's Wrong

TradeXV2 has **92 validated findings** across 10 categories. The root cause is a single architectural cancer: **`tradex/runtime/` (116 Python files) is a coupling hub** that mixes domain abstractions, application orchestration, and infrastructure implementations into one namespace. Everyone imports from it, creating a dependency web instead of a clean DAG.

### What We're Doing

Reorganizing 1,100+ source files into 5 clean layers following the Dependency Rule. This is not incremental cleanup — it's a principled architectural reorganization that eliminates the root cause of all 92 findings simultaneously.

### Key Metrics

| Metric | Before | After |
|---|---|---|
| Clean Architecture layers | 10+ overlapping | 5 clean layers |
| `tradex/runtime/` files | 116 (coupling hub) | 0 (thin facade only) |
| Dependency direction violations | 8+ with ignore_imports workarounds | 0 |
| God classes (>500 lines, >20 methods) | 6 confirmed | 0 |
| True duplicate code modules | 4 pairs | 0 |
| Dead code packages | 4 (providers, interfaces, shared, plugins) | 0 |
| Backward-compat shims | 14 in datalake + plugins | 0 |
| Empty placeholder directories | 5 | 0 |
| Runtime state in source tree | 12 files | 0 |
| `__pycache__` dirs in tree | 227 | 0 |
| Import linter workarounds | 30 | <5 |
| Test files | 642 | 642+ (new decomposition tests) |

---

## 2. Validated Findings Index

### 2.1 God Classes (6 confirmed, 1 borderline)

| # | File | Lines | Classes | Methods | Responsibilities | Severity |
|---|---|---|---|---|---|---|
| G1 | `src/domain/instruments/instrument.py` | 1,161 | 9 | ~52 (Instrument) | Entity + Streaming + Market Data + Trading + Serialization | **CRITICAL** |
| G2 | `tradex/runtime/stream_orchestrator.py` | 1,040 | 6 | ~39 | Session Mgmt + Subscriptions + Message Delivery + Reconnection + Failover | **CRITICAL** |
| G3 | `cli/services/broker_service.py` | 1,070 | 1 | ~31 | Lifecycle + OMS Setup + HTTP + WebSocket + Orders + Broker Switching | **CRITICAL** |
| G4 | `brokers/upstox/gateway.py` | 1,036 | 4 | ~48 | Market Data + Orders + Portfolio + Streaming + Options + Search | **CRITICAL** |
| G5 | `brokers/dhan/orders.py` | 876 | 2 | ~27 | Validation + Placement + Cancellation + Slicing + Idempotency | **HIGH** |
| G6 | `application/oms/order_manager.py` | 838 | 3 | ~28 | Placement + Validation + Idempotency + Cancellation + Trade Recording | **HIGH** |
| G7 | `brokers/upstox/mappers/domain_mapper.py` | 714 | 1 | ~36 | Wire-format mapping (narrow but large) | **MEDIUM** |

### 2.2 Duplicate Code (4 confirmed pairs)

| # | Duplicate A | Duplicate B | Lines Each | Status | Severity |
|---|---|---|---|---|---|
| D1 | `tradex/runtime/observability/http_server.py` | `infrastructure/observability/http_server.py` | 462 vs 479 | **TRUE DUPLICATE** — different versions of same server | **CRITICAL** |
| D2 | `analytics/scanner/rules/engine.py` | `datalake/scanner/engine.py` | 147 vs 147 | **TRUE DUPLICATE** — identical code, different imports | **HIGH** |
| D3 | `analytics/scanner/rules/compiler.py` | `datalake/scanner/compiler.py` | 112 vs 112 | **TRUE DUPLICATE** — identical code, different imports | **HIGH** |
| D4 | `brokers/dhan/resilience/circuit_breaker.py` vs `tradex/runtime/resilience/circuit_breaker.py` | — | 119 vs 179 | **NOT duplicate** — Dhan is a factory wrapping the core CB | **INFO** |
| D5 | `plugins/indicators/{atr,macd,rsi,vwap}.py` vs `domain/indicators/{atr,macd,rsi,vwap}.py` | — | 4 vs 45-61 each | **Shims** — plugins re-export from domain, not real code | **LOW** |
| D6 | `src/domain/options/greeks.py` vs `datalake/analytics/options_greeks.py` | — | 40 vs 224 | **NOT duplicate** — VO vs computation engine (complementary) | **INFO** |

### 2.3 Dead Code (4 packages + empty dirs + stale files)

| # | Target | Files | Status | Severity |
|---|---|---|---|---|
| DC1 | `providers/` | 3 files (deprecated shims, only 1 test imports it) | **DELETE** | **HIGH** |
| DC2 | `interfaces/` | 4 files (all re-exports, zero inbound imports) | **DELETE** | **HIGH** |
| DC3 | `shared/` | 2 files (re-exports 4 types from tradex.runtime) | **DELETE** | **HIGH** |
| DC4 | `plugins/` | 14 files (mostly empty `__init__.py`, indicators are shims) | **DELETE** | **HIGH** |
| DC5 | `application/backtest/` | Empty directory | **DELETE** | **MEDIUM** |
| DC6 | `application/scanner/` | Empty directory | **DELETE** | **MEDIUM** |
| DC7 | `tradex/runtime/ports/` | Empty directory | **DELETE** | **MEDIUM** |
| DC8 | `analytics_cache/` | Empty directory | **DELETE** | **LOW** |
| DC9 | `runtime-dev/` | Empty directory | **DELETE** | **LOW** |
| DC10 | `poc/` | 21 prototype files, no tests | **ARCHIVE** | **MEDIUM** |
| DC11 | `providers/dhan/data_provider.py` line 217 | `from decimal import Decimal` at bottom of file | **Code smell** | **LOW** |

### 2.4 Backward-Compat Shims (16 in datalake + 2 deprecated stubs)

| # | Shim File | Canonical Target |
|---|---|---|
| S1 | `datalake/schema.py` | `datalake.core.schema` |
| S2 | `datalake/nse_calendar.py` | `datalake.core.nse_calendar` |
| S3 | `datalake/migrations.py` | `datalake.core.migrations` |
| S4 | `datalake/option_format.py` | `datalake.core.option_format` |
| S5 | `datalake/pit_joins.py` | `datalake.core.pit_joins` |
| S6 | `datalake/validation.py` | `datalake.quality.validation` |
| S7 | `datalake/quality_universe.py` | `datalake.quality.universe` |
| S8 | `datalake/research_dataset.py` | `datalake.research.dataset` |
| S9 | `datalake/scan_store.py` | `datalake.research.scan_store` |
| S10 | `datalake/scanner_universe.py` | `datalake.research.scanner_universe` |
| S11 | `datalake/sync_options.py` | `datalake.ingestion.sync_options` |
| S12 | `datalake/updater.py` | `datalake.ingestion.updater` |
| S13 | `datalake/options_analytics_sql.py` | `datalake.analytics.options_analytics_sql` |
| S14 | `datalake/options_greeks.py` | `datalake.analytics.options_greeks` |
| S15 | `datalake/run_backtest.py` | `analytics.backtest.run_backtest` (raises ImportError) |
| S16 | `datalake/fast_backtest.py` | `analytics.backtest.fast_backtest` (raises ImportError) |

### 2.5 Dependency Direction Violations

| # | Violation | Current Workaround | Root Cause |
|---|---|---|---|
| V1 | `application/composer/*` → `tradex.runtime.{router,stream_orchestrator,provenance,infrastructure}` | `ignore_imports` in import linter | tradex.runtime mixes layers |
| V2 | `brokers.common` → `tradex.runtime.{resilience.errors, capabilities, broker_port}` | None (passes because not forbidden) | tradex.runtime contains domain types |
| V3 | `application.oms.tests.*` → `infrastructure.{event_bus,event_log,lifecycle,observability,persistence,metrics}` | 7 `ignore_imports` workarounds | Application tests import infrastructure |
| V4 | `cli.services.broker_facade` → `brokers.**` | `ignore_imports` | CLI bypasses abstraction layer |
| V5 | `cli.services.broker_registry` → `brokers.{dhan.factory,upstox.factory,...}` | `ignore_imports` | CLI directly wires broker implementations |
| V6 | Circular: `tradex.runtime` imports `domain.*` → `application` imports `tradex.runtime` → `brokers.common` imports `tradex.runtime` → `brokers.common` imports `domain.*` | None | tradex.runtime is the coupling hub |

**Total import linter workarounds: 30** (should be <5 after reorganization)

### 2.6 SOLID Violations

| # | Violation | File | Lines | Severity |
|---|---|---|---|---|
| SOL1 | **SRP**: Instrument has 4+ distinct responsibilities | `src/domain/instruments/instrument.py` | 1,161 | **CRITICAL** |
| SOL2 | **SRP**: StreamOrchestrator has 5 distinct responsibilities | `tradex/runtime/stream_orchestrator.py` | 1,040 | **CRITICAL** |
| SOL3 | **SRP**: BrokerService is a monolith | `cli/services/broker_service.py` | 1,070 | **CRITICAL** |
| SOL4 | **SRP**: OrderManager handles idempotency+validation+placement+recording | `application/oms/order_manager.py` | 838 | **HIGH** |
| SOL5 | **SRP**: UpstoxBrokerGateway does everything | `brokers/upstox/gateway.py` | 1,036 | **HIGH** |
| SOL6 | **ISP**: CommonBrokerGateway has 14+ methods | `tradex/runtime/broker_port.py` | 178 | **MEDIUM** |
| SOL7 | **DIP**: CLI directly constructs broker implementations | `cli/services/broker_registry.py` | — | **MEDIUM** |
| SOL8 | **OCP**: capability_manifest.py has 1,279 lines of hardcoded catalog | `src/domain/capability_manifest.py` | 1,279 | **MEDIUM** |
| SOL9 | **SRP**: OrdersAdapter does validation+placement+cancellation+slicing | `brokers/dhan/orders.py` | 876 | **HIGH** |
| SOL10 | **SRP**: UpstoxDomainMapper has 36 static mapping methods | `brokers/upstox/mappers/domain_mapper.py` | 714 | **MEDIUM** |

### 2.7 Tight Coupling

| # | Coupling | Between | Severity |
|---|---|---|---|
| TC1 | `application/composer/factory.py` imports 8 modules from `tradex.runtime` | application ↔ tradex.runtime | **CRITICAL** |
| TC2 | `brokers/dhan/factory.py` imports 8 modules from `tradex.runtime` | brokers ↔ tradex.runtime | **HIGH** |
| TC3 | `api_server.py` imports from `tradex.runtime`, `infrastructure`, `runtime` simultaneously | api ↔ 3 layers | **HIGH** |
| TC4 | `brokers/common/` depends on `tradex.runtime` for error types, capabilities, broker_port | common broker ↔ runtime | **MEDIUM** |
| TC5 | `datalake/gateway.py` imports from `tradex.runtime.capabilities` | datalake ↔ tradex.runtime | **MEDIUM** |

### 2.8 Over-Engineering

| # | Issue | File/Lines | Severity |
|---|---|---|---|
| OE1 | capability_manifest.py: 1,279 lines of hardcoded catalog data | `src/domain/capability_manifest.py` | **MEDIUM** |
| OE2 | 35 test markers in pyproject.toml (granularity may be excessive) | `pyproject.toml` | **LOW** |
| OE3 | `analytics/__init__.py` has 598 lines of re-exports | `analytics/__init__.py` | **MEDIUM** |
| OE4 | config/profiles/ has 3-class hierarchy for env profiles | `config/profiles/` | **LOW** |
| OE5 | Two CI mutation testing workflows (`mutation_testing.yml` + `mutation_nightly.yml`) | `.github/workflows/` | **LOW** |

### 2.9 Under-Engineering

| # | Issue | Detail | Severity |
|---|---|---|---|
| UE1 | Pre-commit pytest-smoke hook has wrong paths | References `tests/brokers/*/tests/` instead of `brokers/*/tests/` | **MEDIUM** |
| UE2 | Duplicate `contract` marker in pyproject.toml | Defined on both line ~62 and ~94 | **LOW** |
| UE3 | `api/` not in coverage source | 46 tests exist but not measured by coverage | **MEDIUM** |
| UE4 | 227 `__pycache__` dirs committed to git | `.gitignore` has rule but dirs are already tracked | **MEDIUM** |
| UE5 | Runtime state files in source tree | SQLite, lock, JSON, log files committed | **HIGH** |
| UE6 | `reports/` contains design docs, not reports | Should be in `docs/` | **LOW** |

### 2.10 Code Smells (Naming)

| # | Issue | Example | Severity |
|---|---|---|---|
| CS1 | Mixed verb/noun naming | `updater.py` vs `update_service.py` vs `service.py` | **LOW** |
| CS2 | Inconsistent module depth | `brokers/dhan/` has 60+ files flat; `brokers/upstox/` uses 15 subdirs | **MEDIUM** |
| CS3 | `application/oms/_internal/` convention | Public API surface unclear | **MEDIUM** |
| CS4 | `tradex.runtime.resilience.errors` imported as "domain errors" | Error hierarchy in wrong layer | **HIGH** |

---

## 3. Repository Inventory

| Module | Files (py) | Subdirs | Tests? | Status | Action |
|---|---|---|---|---|---|
| `src/domain/` | 230 | 30+ | ✅ 39 | Core domain — well-structured | **KEEP** (promote to root) |
| `brokers/` | 422 | dhan/upstox/paper/common | ✅ 158 | Largest module | **RESTRUCTURE** (dhan flat → subdirs) |
| `tradex/runtime/` | 116 | 12 | ✅ 19 | **COUPLING HUB** | **DISSOLVE** into domain/app/infra |
| `analytics/` | ~130 | 25 | ✅ 23 | Feature-rich, some duplication | **CONSOLIDATE** (scanner/indicators) |
| `datalake/` | ~90 | 11 | ✅ 37 | Has shims + real files mixed | **CLEAN** (remove 16 shims) |
| `infrastructure/` | 82 | 13 | ✅ 19 | Overlaps with tradex.runtime | **MERGE** into tradex.runtime/core |
| `cli/` | ~97 | 7 | ✅ 32 | Well-organized | **KEEP** |
| `api/` | 43 | 4 | ✅ 46 (in tests/) | Clean, thin layer | **KEEP** |
| `application/` | ~60 | 7 | ❌ 0 | OMS-heavy, 2 empty dirs | **EXPAND** (receive runtime orchestration) |
| `tests/` | 218 | 21 | — | Comprehensive test suite | **KEEP** + add decomposition tests |
| `config/` | 20 | 2 | ✅ 6 | Small, focused | **KEEP** |
| `providers/` | 3 | 1 | ❌ 1 test | **DEPRECATED DEAD CODE** | **DELETE** |
| `interfaces/` | 4 | 3 | ❌ | **EMPTY SHELL** | **DELETE** |
| `shared/` | 2 | 0 | ❌ | **2-file re-export shim** | **DELETE** |
| `tradex/` (root) | 2 | 1 | ❌ | 2 files + massive runtime | **RESTRUCTURE** (runtime → facade) |
| `plugins/` | 14 | 4 | ❌ | Mostly empty `__init__.py` | **DELETE** |
| `scripts/` | 45 | 3 | — | Unstructured utility dump | **CATEGORIZE** |
| `reports/` | 15 | 0 | — | Design docs, not reports | **MOVE to docs/** |
| `poc/` | 21 | 1 | — | Prototypes, no tests | **ARCHIVE** |
| `runtime/` | ~10 | 0 | — | Runtime state (sqlite, locks, json) | **GITIGNORE** |
| `analytics_cache/` | 0 | 0 | — | Empty | **DELETE** |
| `runtime-dev/` | 0 | 0 | — | Empty | **DELETE** |

**Total test files: 642** | **Total `__pycache__` dirs: 227** | **Import linter workarounds: 30**

---

## 4. Architecture Root Cause Analysis

### The One Problem That Causes Everything Else

`tradex/runtime/` (116 files) mixes three Clean Architecture layers:

| What's in `tradex/runtime/` | Should Be In | Why |
|---|---|---|
| `broker_port.py`, `capabilities.py`, `models.py`, `errors.py`, `policy.py`, `extensions/`, `options/` | **`domain/`** | Domain abstractions — the business vocabulary |
| `router.py`, `registry.py`, `stream_orchestrator.py`, `historical_coordinator.py`, `quota_scheduler.py`, `provenance.py`, `services/`, `reconciliation/` | **`application/`** | Orchestration — wiring domain use cases |
| `auth/`, `resilience/`, `observability/`, `connection/`, `connection_pool.py`, `settings.py`, `clock.py`, `adapters/`, `mappers/` | **`infrastructure/`** | Concrete implementations of external concerns |

### The Proof: Import Map

`application/composer/factory.py` — application importing what should be domain types:

```python
from tradex.runtime.broker_port import CommonBrokerGateway      # ← domain type
from tradex.runtime.historical_coordinator import HistoricalQuery  # ← application type
from tradex.runtime.router import BrokerRouter                     # ← application type
from tradex.runtime.stream_orchestrator import StreamOrchestrator  # ← application type
from tradex.runtime.registry import BrokerRegistry                 # ← application type
from tradex.runtime.policy import SourceSelectionPolicy            # ← domain type
from tradex.runtime.infrastructure import BrokerInfrastructure     # ← infrastructure type
```

### How It Causes All 92 Findings

| Finding Category | Root Cause |
|---|---|
| 6 God Classes | tradex.runtime bundles too many concerns → classes grow to accommodate everything |
| 4 Duplicates | Two implementations exist because there's no single canonical layer |
| 30 ignore_imports | Workarounds for violations caused by the coupling hub |
| 6 Dependency violations | Application/brokers import from a package that mixes all layers |
| 10 SOLID violations | Layer confusion makes OCP/ISP/DIP impossible to apply |
| 5 Tight couplings | Everything imports tradex.runtime → shotgun surgery |

### The Dependency Web vs The DAG

```
CURRENT (Dependency Web):              TARGET (Clean DAG):

       domain                              domain
         ↑                                   ↑
    tradex.runtime ←── COUPLING HUB     application
      ↑    ↑    ↑        ↑                ↑
  application brokers api cli     infrastructure
                    ↑                ↑         ↑
               infrastructure     brokers   analytics
                                       ↑     datalake
                                       ↑
                                    api, cli
```

---

## 5. Clean Architecture Target State

### The Dependency Rule (Bob Martin, Clean Architecture Ch. 5)

> *"Source code dependencies must point only inward, toward higher-level policies."*

1. **Domain** imports NOTHING from outer layers
2. **Application** imports ONLY from domain
3. **Infrastructure** imports ONLY from domain (to implement ports)
4. **Brokers** import ONLY from domain (to implement broker ports)
5. **Interface** (API/CLI) imports ONLY from application

### Target Structure

```
Trade_XV2/
├── src/domain/              # CORE DOMAIN (stable center, ~265 files after moves)
│   ├── entities/
│   ├── events/
│   ├── instruments/         # Decomposed from god class
│   ├── indicators/          # Single source of truth
│   ├── models/
│   ├── options/
│   ├── extensions/
│   ├── errors.py            # Error hierarchy (moved from tradex.runtime)
│   ├── ports/               # Broker gateway protocols
│   │   ├── broker_gateway.py  # from tradex/runtime/broker_port.py
│   │   ├── market_data.py
│   │   ├── order.py
│   │   └── stream.py
│   ├── policies/
│   │   └── source_selection.py  # from tradex/runtime/policy.py
│   ├── scanners/            # Domain scanner ABC only
│   └── value_objects/       # from tradex/runtime/capabilities.py
│
├── application/             # USE CASES (~110 files after moves)
│   ├── oms/
│   │   ├── order_manager.py    # Decomposed from 838 → ~300 lines
│   │   ├── idempotency_guard.py  # Extracted
│   │   ├── order_validator.py    # Extracted
│   │   ├── trade_recorder.py     # Extracted
│   │   ├── reconciliation/       # from tradex/runtime/reconciliation/
│   │   └── risk_manager.py
│   ├── execution/
│   │   └── submission_pipeline.py  # from tradex/runtime/
│   ├── composer/
│   │   ├── router.py             # from tradex/runtime/router.py
│   │   ├── registry.py           # from tradex/runtime/registry.py
│   │   └── factory.py            # merged with tradex/runtime/factory.py
│   ├── streaming/
│   │   ├── orchestrator.py       # from tradex/runtime/stream_orchestrator.py (decomposed)
│   │   ├── session_manager.py    # Extracted
│   │   ├── tick_router.py        # Extracted
│   │   ├── reconnect_controller.py  # Extracted
│   │   └── candle_aggregator.py  # from tradex/runtime/
│   ├── data/
│   │   ├── historical_coordinator.py  # from tradex/runtime/
│   │   └── provenance.py              # from tradex/runtime/
│   ├── scheduling/
│   │   ├── quota_scheduler.py    # from tradex/runtime/
│   │   └── quota_decorator.py    # from tradex/runtime/
│   ├── services/
│   │   ├── data_validator.py
│   │   ├── download_engine.py
│   │   ├── historical_data.py
│   │   ├── instrument_registry.py
│   │   └── production_readiness.py
│   ├── trading/
│   └── portfolio/
│
├── infrastructure/          # IMPLEMENTATIONS (~162 files, merged from both sources)
│   ├── auth/                # from tradex/runtime/auth/
│   │   ├── token.py
│   │   ├── token_ensure.py
│   │   ├── token_persistence.py
│   │   ├── token_policy.py
│   │   ├── environment_bootstrap.py
│   │   ├── credential_resolver.py
│   │   ├── credential_validator.py
│   │   ├── jwt_expiry.py
│   │   ├── registry.py
│   │   └── totp_cooldown.py
│   ├── resilience/          # SINGLE source of truth
│   │   ├── circuit_breaker.py  # from tradex/runtime/resilience/
│   │   ├── retry.py            # merged from infrastructure/retry.py
│   │   ├── rate_limiter.py
│   │   ├── backoff.py
│   │   └── broker_health_monitor.py
│   ├── observability/
│   │   ├── http_server.py    # SINGLE copy (merge infrastructure/ + tradex/runtime/)
│   │   ├── audit.py          # merged with infrastructure/observability/alerting.py
│   │   ├── health_check.py
│   │   └── tracing.py
│   ├── event_bus/           # from infrastructure/event_bus/
│   ├── cache/               # from infrastructure/cache.py, cache_redis.py
│   ├── persistence/         # from infrastructure/persistence/
│   ├── di/                  # from infrastructure/di.py, di_scopes.py
│   ├── logging/             # from infrastructure/logging_config.py
│   ├── metrics/             # from infrastructure/metrics/
│   ├── connection/          # from tradex/runtime/connection/
│   ├── pool/                # from tradex/runtime/connection_pool.py
│   ├── security/            # from tradex/runtime/ssl_hardening.py
│   ├── config/              # from tradex/runtime/settings.py, env_loader.py
│   ├── time/                # from tradex/runtime/clock.py
│   ├── gateway/             # from tradex/runtime/gateway*.py
│   ├── adapters/            # from tradex/runtime/adapters/
│   ├── mappers/             # from tradex/runtime/mappers/
│   ├── session/             # from tradex/runtime/session_infra.py
│   ├── lifecycle/           # from infrastructure/lifecycle/
│   └── io/                  # from infrastructure/io/
│
├── brokers/                 # BROKER IMPLEMENTATIONS (restructured)
│   ├── common/              # Shared abstractions
│   ├── dhan/                # → RESTRUCTURE: flat → organized subdirs
│   │   ├── api/
│   │   ├── auth/
│   │   ├── config/
│   │   ├── data/
│   │   ├── execution/       # includes orders.py (decomposed)
│   │   ├── streaming/
│   │   ├── resilience/      # Dhan-specific CB config (factory only, no dup)
│   │   └── tests/
│   ├── upstox/              # Already better structured
│   └── paper/
│
├── analytics/               # QUANT ANALYTICS (consolidated)
│   ├── scanner/             # SINGLE scanner (merge datalake/scanner/ in)
│   │   ├── engine.py        # from analytics/scanner/rules/
│   │   ├── compiler.py
│   │   └── models.py
│   ├── indicators/          # HalfTrend, MarketStructure (domain has ATR/MACD/RSI/VWAP)
│   ├── backtest/
│   └── ...
│
├── datalake/                # DATA STORAGE (shims removed)
│   ├── core/
│   ├── ingestion/
│   ├── analytics/
│   ├── quality/
│   ├── storage/
│   ├── mcp/
│   └── research/
│
├── api/                     # REST/WEBSOCKET (unchanged)
├── cli/                     # CLI + TUI (BrokerService decomposed)
├── config/                  # Configuration (unchanged)
├── tests/                   # Test suite (architecture tests updated)
├── tradex/                  # PUBLIC SDK (thin facade only)
│   ├── __init__.py          # Re-exports BrokerSession
│   ├── session.py           # Public API entry point
│   └── runtime/
│       └── __init__.py      # Backward-compat facade (thin re-exports)
│
├── scripts/                 # Utility scripts (categorized)
│   ├── audit/
│   ├── debug/
│   ├── migration/
│   └── verify/
│
├── docs/                    # Documentation (reports/*.md moved here)
└── poc/                     # Archived prototypes (moved from root)
```

---

## 6. Phased Execution Plan

### Overview: 10 Phases, Dependency-Ordered

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7 ──► Phase 8 ──► Phase 9
(Branch)    (Hygiene)   (Facade)    (Domain)    (App)       (Infra)     (God Class) (Dhan)     (CI/Gov)    (Final)
                                                                                                               │
                                                                                                               ▼
                                                                                                         PHASE 10
                                                                                                         (Cleanup)
```

---

### PHASE 0: Branch & Checkpoint ✅ COMPLETE

**Status:** Done. Branch `refactor/structural-cleanup` at commit `ee8fe75`.

---

### PHASE 1: Hygiene & Dead Code Deletion

> **Risk:** LOW — Removing code with zero or near-zero imports  
> **Agents:** Agent-α (primary), Agent-ζ (validate)  
> **Duration:** 2–3 hours  
> **Depends on:** Phase 0 ✅  
> **Can parallelize with:** Nothing (first phase)

#### 1.1 Fix `.gitignore` and remove tracked artifacts

```bash
# Ensure these patterns are in .gitignore (verify current state):
__pycache__/
*.py[cod]
*.sqlite
*.sqlite-shm
*.sqlite-wal
*.duckdb
*.duckdb.wal
runtime/*.lock
runtime/*.json
runtime/*.log
market_data/

# Remove __pycache__ from tracking (227 dirs)
find . -type d -name "__pycache__" -not -path "./venv/*" -not -path "./.venv/*" -exec git rm -r --cached {} + 2>/dev/null

# Remove runtime state files from tracking
git rm --cached runtime/dead_letter.sqlite 2>/dev/null
git rm --cached runtime/dhan-market-feed-*.lock 2>/dev/null
git rm --cached runtime/dhan-token-state.json 2>/dev/null
git rm --cached runtime/dhan-totp-cooldown.json 2>/dev/null
git rm --cached runtime/upstox-token-state.json 2>/dev/null
git rm --cached runtime/server.log 2>/dev/null
git rm --cached market_data/*.sqlite 2>/dev/null
git rm --cached market_data/*.sqlite-* 2>/dev/null
```

**Commit:** `chore(gitignore): exclude __pycache__ and runtime state artifacts`

#### 1.2 Delete `providers/` package (deprecated)

| File | Reason |
|---|---|
| `providers/__init__.py` | Deprecated, emits DeprecationWarning |
| `providers/dhan/__init__.py` | Deprecated |
| `providers/dhan/data_provider.py` | Deprecated, replaced by `brokers.dhan.adapter` |
| `providers/dhan/execution_provider.py` | Deprecated re-export |

**Also delete:** `tests/unit/providers/test_dhan_data_provider.py` (only consumer)

```bash
grep -rn "from providers" --include="*.py" . | grep -v __pycache__ | grep -v providers/
# Expected: only the test file
```

**Commit:** `refactor(dead): delete deprecated providers/ package`

#### 1.3 Delete `interfaces/` package (empty shell)

| File | Reason |
|---|---|
| `interfaces/__init__.py` | DeprecationWarning, empty `__all__` |
| `interfaces/cli/__init__.py` | Re-export from cli.main |
| `interfaces/rest/__init__.py` | Re-export from api.main |
| `interfaces/sdk/__init__.py` | Re-export from tradex |

Zero inbound imports confirmed.

**Commit:** `refactor(dead): delete empty interfaces/ package`

#### 1.4 Delete `shared/` package (2-file re-export shim)

| File | Reason |
|---|---|
| `shared/__init__.py` | Re-exports from shared.types |
| `shared/types.py` | Re-exports 4 types from tradex.runtime.capabilities |

Zero inbound imports confirmed.

**Commit:** `refactor(dead): delete shared/ re-export shim`

#### 1.5 Delete `plugins/` package (empty + shims)

| File | Reason |
|---|---|
| `plugins/__init__.py` | Empty |
| `plugins/dhan/__init__.py` | Empty |
| `plugins/paper/__init__.py` | Empty |
| `plugins/upstox/__init__.py` | Empty |
| `plugins/indicators/__init__.py` | Re-exports from domain.indicators |
| `plugins/indicators/atr.py` | 4-line shim |
| `plugins/indicators/macd.py` | 4-line shim |
| `plugins/indicators/rsi.py` | 4-line shim |
| `plugins/indicators/vwap.py` | 4-line shim |

```bash
grep -rn "from plugins" --include="*.py" . | grep -v __pycache__ | grep -v plugins/
# Expected: 0 results
```

**Commit:** `refactor(dead): delete plugins/ package (empty + indicator shims)`

#### 1.6 Delete empty placeholder directories

| Directory | Reason |
|---|---|
| `application/backtest/` | Empty |
| `application/scanner/` | Empty |
| `tradex/runtime/ports/` | Empty |
| `analytics_cache/` | Empty |
| `runtime-dev/` | Empty |

**Commit:** `chore(hygiene): remove empty placeholder directories`

#### 1.7 Delete empty port stubs in domain

| File | Reason |
|---|---|
| `src/domain/ports/data_provider.py` | 0 bytes |
| `src/domain/ports/execution_provider.py` | 0 bytes |
| `src/domain/ports/execution_context.py` | 0 bytes |
| `src/domain/ports/provider_registry.py` | 0 bytes |
| `src/domain/ports/session_context.py` | 0 bytes |
| `src/domain/ports/subscription_handle.py` | 0 bytes |
| `src/domain/composition/__init__.py` | Empty package |
| `src/domain/derivatives/__init__.py` | Empty package |

**Commit:** `refactor(dead): remove empty port/interface stubs`

#### 1.8 Move design docs from `reports/` to `docs/`

```bash
mv reports/*.md docs/
rmdir reports/
```

**Commit:** `docs: move design documents from reports/ to docs/`

#### PHASE 1 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." pytest tests/unit/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
git add -A && git commit -m "Phase 1 complete: hygiene and dead code deletion"
```

---

### PHASE 2: Create tradex.runtime Facade (Safety Net)

> **Risk:** LOW — Just re-exports, no logic changes  
> **Agents:** Agent-γ (primary), Agent-ζ (validate)  
> **Duration:** 1 day  
> **Depends on:** Phase 1 ✅  
> **Key Insight:** By making tradex.runtime a facade FIRST, all subsequent moves are safe

**Goal:** Transform every file in `tradex/runtime/` into a thin re-export shim. No code moves yet. All existing imports continue to work. This is the safety net for the entire reorganization.

#### 2.1 Create canonical target directories

```bash
mkdir -p src/domain/ports
mkdir -p src/domain/value_objects
mkdir -p src/domain/models
mkdir -p src/domain/policies
mkdir -p application/composer
mkdir -p application/streaming
mkdir -p application/data
mkdir -p application/scheduling
mkdir -p application/services
mkdir -p application/oms/reconciliation
```

#### 2.2 Move code to canonical locations (file-by-file)

For each file, the process is:
1. Copy the file to its canonical location
2. Replace the original with a thin re-export shim
3. Run the import linter

**Domain moves (Wave 2 prep):**

| Source | Target |
|---|---|
| `tradex/runtime/broker_port.py` | `src/domain/ports/broker_gateway.py` |
| `tradex/runtime/capabilities.py` | `src/domain/value_objects/capability.py` |
| `tradex/runtime/models.py` | `src/domain/models/routing.py` |
| `tradex/runtime/dtos.py` | `src/domain/models/dtos.py` |
| `tradex/runtime/errors.py` | Merge into `src/domain/errors.py` |
| `tradex/runtime/gateway_errors.py` | Merge into `src/domain/errors.py` |
| `tradex/runtime/policy.py` | `src/domain/policies/source_selection.py` |
| `tradex/runtime/policy_defaults.py` | `src/domain/policies/defaults.py` |
| `tradex/runtime/extensions/` (5 files) | `src/domain/extensions/` |
| `tradex/runtime/options/` (2 files) | `src/domain/options/` |

**Application moves (Wave 3 prep):**

| Source | Target |
|---|---|
| `tradex/runtime/router.py` | `application/composer/router.py` |
| `tradex/runtime/registry.py` | `application/composer/registry.py` |
| `tradex/runtime/factory.py` | Merge into `application/composer/factory.py` |
| `tradex/runtime/stream_orchestrator.py` | `application/streaming/orchestrator.py` |
| `tradex/runtime/candle_aggregator.py` | `application/streaming/candle_aggregator.py` |
| `tradex/runtime/historical_coordinator.py` | `application/data/historical_coordinator.py` |
| `tradex/runtime/provenance.py` | `application/data/provenance.py` |
| `tradex/runtime/quota_scheduler.py` | `application/scheduling/quota_scheduler.py` |
| `tradex/runtime/quota_decorator.py` | `application/scheduling/quota_decorator.py` |
| `tradex/runtime/submission_pipeline.py` | `application/execution/submission_pipeline.py` |
| `tradex/runtime/reconciliation/` | `application/oms/reconciliation/` |
| `tradex/runtime/services/` (8 files) | `application/services/` |

**Infrastructure moves (Wave 4 prep):**

| Source | Target |
|---|---|
| `tradex/runtime/auth/` (12 files) | `infrastructure/auth/` |
| `tradex/runtime/resilience/` (7 files) | `infrastructure/resilience/` (merge with existing) |
| `tradex/runtime/observability/` (4 files) | `infrastructure/observability/` (merge, pick best) |
| `tradex/runtime/connection/` (4 files) | `infrastructure/connection/` |
| `tradex/runtime/connection_pool.py` | `infrastructure/pool/connection_pool.py` |
| `tradex/runtime/ssl_hardening.py` | `infrastructure/security/ssl_hardening.py` |
| `tradex/runtime/settings.py` | `infrastructure/config/settings.py` |
| `tradex/runtime/env_loader.py` | `infrastructure/config/env_loader.py` |
| `tradex/runtime/clock.py` | `infrastructure/time/clock.py` |
| `tradex/runtime/build_info.py` | `infrastructure/build_info.py` |
| `tradex/runtime/async_compat.py` | `infrastructure/async/compat.py` |
| `tradex/runtime/infrastructure.py` | `infrastructure/broker_infrastructure.py` |
| `tradex/runtime/gateway.py` | `infrastructure/gateway/base.py` |
| `tradex/runtime/gateway_execution.py` | `infrastructure/gateway/execution.py` |
| `tradex/runtime/gateway_factory.py` | `infrastructure/gateway/factory.py` |
| `tradex/runtime/session_infra.py` | `infrastructure/session/infra.py` |
| `tradex/runtime/adapters/` | `infrastructure/adapters/` |
| `tradex/runtime/mappers/` | `infrastructure/mappers/` |

#### 2.3 Replace original files with thin shims

After each move, replace the original `tradex/runtime/X.py` with:

```python
"""Backward-compat facade — canonical location: <target>"""
from <target_module> import *  # noqa: F401,F403
```

This means **zero breaking changes** for existing importers.

#### 2.4 Handle infrastructure/merge conflicts

When merging `infrastructure/` with `tradex/runtime/` files:
- `infrastructure/observability/http_server.py` (479L) vs `tradex/runtime/observability/http_server.py` (462L): **Keep the tradex.runtime version** (newer, tested), delete infrastructure version
- `infrastructure/retry.py` vs `tradex/runtime/resilience/retry.py`: **Keep tradex.runtime version**, delete infrastructure version
- All other infrastructure files: move to `infrastructure/` proper (they're already there)

#### 2.5 Delete datalake shims

Replace all 14 datalake root shims + 2 deprecated stubs with canonical imports:

```bash
# Before deleting, find all consumers:
grep -rn "from datalake.schema import\|from datalake.nse_calendar import\|..." --include="*.py" .
# Update imports to canonical paths, then delete shims
```

#### PHASE 2 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest datalake/tests/ -x -q
PYTHONPATH="src:." pytest src/domain/tests/ -x -q
git add -A && git commit -m "Phase 2 complete: facade created, all moves done"
```

---

### PHASE 3: Consolidate Duplicates

> **Risk:** MEDIUM — Merging identical code  
> **Agents:** Agent-β (primary), Agent-ζ (validate)  
> **Duration:** 4–6 hours  
> **Depends on:** Phase 2 ✅  
> **Can parallelize with:** Phase 4 (god class decomposition)

#### 3.1 Consolidate scanner implementations

**Current state:**
- `analytics/scanner/rules/engine.py` (147L) ≡ `datalake/scanner/engine.py` (147L) — **IDENTICAL**
- `analytics/scanner/rules/compiler.py` (112L) ≡ `datalake/scanner/compiler.py` (112L) — **IDENTICAL**
- `analytics/scanner/rules/models.py` ≠ `datalake/scanner/models.py` — different schemas

**Action:**
1. Keep `analytics/scanner/rules/` as the canonical location
2. Update `datalake/scanner/` to import from `analytics.scanner.rules`
3. Or delete `datalake/scanner/` entirely if `datalake/research/` can import directly

```bash
# Find all consumers of datalake.scanner
grep -rn "from datalake.scanner" --include="*.py" . | grep -v __pycache__
```

**Commit:** `refactor(scanner): consolidate duplicate scanner engine/compiler`

#### 3.2 Consolidate HTTP server

**Current state:**
- `infrastructure/observability/http_server.py` (479L) — uses `ManagedService` from `infrastructure.lifecycle`
- `tradex/runtime/observability/http_server.py` (462L) — uses `ManagedService` from `infrastructure.lifecycle`

**Action:**
1. Diff the two files to identify differences
2. Keep the more complete version (likely tradex.runtime — newer)
3. Update the other to import from the canonical location

**Commit:** `refactor(observability): consolidate duplicate HTTP server`

#### 3.3 Consolidate indicators

**Current state:**
- `src/domain/indicators/{atr,macd,rsi,vwap}.py` — canonical domain implementations ✅
- `analytics/indicators/halftrend.py`, `market_structure.py` — different indicators (not duplicates)

**Action:**
1. Move `analytics/indicators/halftrend.py` → `src/domain/indicators/halftrend.py`
2. Move `analytics/indicators/market_structure.py` → `src/domain/indicators/market_structure.py`
3. Verify `analytics/pipeline/features.py` imports from `domain.indicators` (not local copies)

```bash
PYTHONPATH="src:." pytest src/domain/tests/ analytics/tests/ -x -q -k "indicator"
```

**Commit:** `refactor(indicators): consolidate all indicator definitions in domain`

#### 3.4 Reduce `analytics/__init__.py` mega re-export

**Current:** 598 lines, 22 re-exports  
**Target:** ~30 lines — essential public API only. Consumers should import directly from sub-modules.

**Commit:** `refactor(analytics): reduce mega re-export to essential public API`

#### PHASE 3 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest datalake/tests/ analytics/tests/ -x -q
```

---

### PHASE 4: God Class Decomposition

> **Risk:** HIGH — Behavioral changes, requires careful test coverage  
> **Agents:** Agent-δ (primary), Agent-ε (test repair), Agent-ζ (validate)  
> **Duration:** 3–4 days  
> **Depends on:** Phase 2 ✅ (can overlap with Phase 3)  
> **Can parallelize:** 4a, 4b, 4c can run on separate agents

#### 4a. Decompose `Instrument` (1,161 lines → ~4 classes)

**Current class layout:**
```
Instrument (1,161 lines, 9 classes total)
├── Instrument [55-777] — entity + streaming + market data + trading (~722 lines)
├── Equity [785-794]
├── ETF [797-806]
├── Spot [809-818]
├── Currency [821-830]
├── Index [833-842]
├── Future [845-861]
├── Commodity [864-981]
└── Option [984-1161]
```

**Target structure:**
```
src/domain/instruments/
├── instrument.py              ← Entity only (~300 lines): id, symbol, exchange, properties, state
├── instrument_streaming.py    ← Streaming mixin (~150 lines): subscribe, callbacks, reconnect
├── instrument_market_data.py  ← Market data queries (~200 lines): quote, depth, history, options
├── instrument_trading.py      ← Trading actions (~200 lines): buy, sell, cancel, modify
├── equity.py                  ← Equity subclass (keep separate)
├── etf.py                     ← ETF subclass
├── spot.py                    ← Spot subclass
├── currency.py                ← Currency subclass
├── index.py                   ← Index subclass
├── future.py                  ← Future subclass
├── commodity.py               ← Commodity subclass
└── option.py                  ← Option subclass
```

**Composition pattern:**
```python
class Instrument(InstrumentStreaming, InstrumentMarketData, InstrumentTrading):
    """Unified instrument facade — composition over god class."""
    pass
```

**Validation:**
```bash
PYTHONPATH="src:." pytest src/domain/tests/test_instrument.py -x -v
PYTHONPATH="src:." pytest tests/unit/domain/instruments/ -x -v
```

**Commit:** `refactor(domain): decompose Instrument god class into 4 focused mixins`

#### 4b. Decompose `StreamOrchestrator` (1,040 lines → ~5 classes)

**Current layout:**
```
StreamOrchestrator [219-1040] (~822 lines, ~28 methods)
├── Session Management: start, stop, open, disconnect
├── Subscription Routing: subscribe, unsubscribe, merge
├── Message Delivery: tick, order update, dedup
├── Reconnection: reconnect loop, failover, heartbeat
└── Broker Selection: select_broker
```

**Target structure:**
```
application/streaming/
├── orchestrator.py          ← Thin orchestrator (~250 lines): wires the collaborators
├── session_manager.py       ← Session lifecycle (~200 lines)
├── tick_router.py           ← Message delivery + dedup (~200 lines)
├── reconnect_controller.py  ← Reconnect + failover + heartbeat (~250 lines)
└── broker_selector.py       ← Broker selection logic (~100 lines)
```

**Commit:** `refactor(streaming): decompose StreamOrchestrator into 5 focused classes`

#### 4c. Decompose `BrokerService` (1,070 lines → ~4 classes)

**Current layout:**
```
BrokerService [48-1070] (~1,023 lines, ~31 methods)
├── Lifecycle: start, stop, close
├── OMS Setup: _build_oms_risk_manager, _build_and_register_oms
├── Order Routing: place_order, cancel_order, get_orders
└── Broker Management: set_active_broker, use_paper, get_broker_statuses
```

**Target structure:**
```
cli/services/
├── broker_service.py       ← Thin orchestrator (~200 lines)
├── oms_bootstrap.py        ← OMS setup and DI wiring (~200 lines)
├── cli_broker_facade.py    ← Order routing for CLI (~200 lines)
└── broker_manager.py       ← Active broker switching (~150 lines)
```

**Commit:** `refactor(cli): decompose BrokerService god class`

#### 4d. Decompose `UpstoxBrokerGateway` (1,036 lines → ~4 classes)

**Target:**
```
brokers/upstox/
├── gateway.py               ← Thin facade (~200 lines)
├── market_data_gateway.py   ← LTP, quote, depth, history (~300 lines)
├── order_gateway.py         ← Place, cancel, modify, orderbook (~250 lines)
├── streaming_gateway.py     ← WebSocket connections, tick parsing (~300 lines)
└── portfolio_gateway.py     ← Positions, holdings, balance (~150 lines)
```

**Commit:** `refactor(upstox): decompose UpstoxBrokerGateway into focused adapters`

#### 4e. Decompose `OrdersAdapter` (876 lines → ~3 classes)

**Target:**
```
brokers/dhan/execution/
├── orders.py                 ← Thin orchestrator (~200 lines)
├── order_validator.py        ← Validation rules (~200 lines)
├── order_placement.py        ← Placement + slicing + idempotency (~300 lines)
└── order_cancellation.py     ← Cancellation + modification (~150 lines)
```

**Commit:** `refactor(dhan): decompose OrdersAdapter into focused collaborators`

#### 4f. Decompose `OrderManager` (838 lines → ~4 classes)

**Target:**
```
application/oms/
├── order_manager.py          ← Thin orchestrator (~250 lines)
├── idempotency_guard.py      ← Idempotency logic (~150 lines)
├── order_validator.py        ← Validation logic (~150 lines)
└── trade_recorder.py         ← Trade recording + events (~200 lines)
```

**Commit:** `refactor(oms): decompose OrderManager into focused collaborators`

#### PHASE 4 GATE
```bash
PYTHONPATH="src:." pytest src/domain/tests/test_instrument.py -x -v
PYTHONPATH="src:." pytest tests/unit/ -x -q
PYTHONPATH="src:." pytest cli/tests/ -x -q
PYTHONPATH="src:." pytest tests/api/ -x -q
PYTHONPATH="src:." pytest application/oms/tests/ -x -q
```

---

### PHASE 5: Fix SOLID & Dependency Direction

> **Risk:** MEDIUM-HIGH — Architectural fixes  
> **Agents:** Agent-γ (dependency direction), Agent-δ (SOLID), Agent-ζ (validate)  
> **Duration:** 1–2 days  
> **Depends on:** Phase 4 ✅  
> **Can parallelize:** 5a and 5b on separate agents

#### 5a. Move error hierarchy to domain layer

**Current:** `tradex/runtime/resilience/errors.py` contains `TradeXV2Error` hierarchy  
**Problem:** Error types used by `brokers.common`, `application`, `api` all depend on `tradex.runtime`

**Action:**
1. Move error hierarchy to `src/domain/errors.py` (extend existing)
2. Create re-export in `infrastructure/resilience/errors.py` for backward compat
3. Update `brokers/common/api/__init__.py` to import from `domain.errors`

**Commit:** `refactor(domain): move error hierarchy to domain layer`

#### 5b. Split CommonBrokerGateway into focused protocols (ISP fix)

**Current:** `CommonBrokerGateway` has 14+ methods in one protocol  
**Target:**
```python
class MarketDataGateway(Protocol):
    def ltp(...) -> Decimal: ...
    def quote(...) -> Quote: ...
    def depth(...) -> MarketDepth: ...
    def history(...) -> pd.DataFrame: ...

class OrderGateway(Protocol):
    def place_order(...) -> OrderResponse: ...
    def cancel_order(...) -> OrderResponse: ...
    def modify_order(...) -> OrderResponse: ...

class StreamGateway(Protocol):
    def stream(...) -> StreamHandle: ...
    def unstream(...) -> None: ...

# Backward compat composite
class CommonBrokerGateway(MarketDataGateway, OrderGateway, StreamGateway, Protocol):
    ...
```

**Commit:** `refactor(ports): split CommonBrokerGateway into focused protocols`

#### 5c. Fix CLI broker abstraction leak

**Current:** `cli.services.broker_facade` imports directly from `brokers.**`  
**Current:** `cli.services.broker_registry` imports from `brokers.{dhan,upstox,paper}.factory`

**Action:**
1. Create `application/broker_registry.py` — application-level broker registration
2. CLI imports from application, not directly from brokers
3. Remove 8 `ignore_imports` workarounds

**Commit:** `refactor(cli): route broker registration through application layer`

#### 5d. Remove stale `ignore_imports` workarounds

After all the above moves, audit each of the 30 workarounds:
- Some will be resolved (error types now in domain, facade handles rest)
- Some test-only ignores are legitimate (tests can import across layers for setup)
- Target: reduce from 30 to <5

**Commit:** `refactor(import-linter): remove resolved workarounds`

#### 5e. Fix `TradingContext` pattern

**Note:** `TradingContext` does NOT exist as a standalone file (validated). It's a property on `BrokerService` (line 712) and a parameter in analytics engines.

**Action:** After BrokerService decomposition (Phase 4c), the TradingContext pattern will be naturally eliminated. Verify no dangling references remain.

#### PHASE 5 GATE
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." lint-imports --config pyproject.toml
PYTHONPATH="src:." pytest application/oms/tests/ -x -q
PYTHONPATH="src:." pytest brokers/common/tests/ -x -q
# Verify ignore_imports count:
grep -c "ignore_imports" pyproject.toml
```

---

### PHASE 6: Restructure `brokers/dhan/`

> **Risk:** MEDIUM — File moves within a package  
> **Agents:** Agent-γ (primary), Agent-ε (test repair), Agent-ζ (validate)  
> **Duration:** 1–2 days  
> **Depends on:** Phase 4e ✅  
> **Can parallelize with:** Phase 7

**Current state:** 60+ files flat at root of `brokers/dhan/`

**Target structure:**
```
brokers/dhan/
├── __init__.py
├── factory.py              ← Broker construction
├── config.py               ← Dhan-specific config
├── settings.py             ← Environment settings
├── api/                    ← HTTP/REST client
│   ├── http_client.py
│   ├── async_http_client.py
│   └── requests_client.py
├── auth/                   ← Authentication
│   ├── token_scheduler.py
│   ├── totp_client.py
│   ├── session_manager.py
│   └── credential_resolver.py
├── data/                   ← Market data
│   ├── gateway.py
│   ├── market_feed.py
│   └── websocket.py
├── execution/              ← Order execution (decomposed from orders.py)
│   ├── orders.py
│   ├── order_validator.py
│   ├── order_placement.py
│   └── order_cancellation.py
├── streaming/              ← Real-time streaming
│   ├── connection.py
│   └── market_feed.py
├── resilience/             ← Dhan-specific resilience
│   ├── circuit_breaker.py  ← Factory only (core CB is in infrastructure)
│   └── retry_executor.py
├── extensions/             ← Dhan-specific extensions
├── common_extensions.py
├── capabilities.py
├── gateway.py
├── reconciliation.py
├── batch_executor.py
├── domain_mapper.py
└── tests/
    ├── unit/
    ├── integration/
    ├── regression/
    └── contract/
```

**Action:** Move files into subdirectories, update all internal imports, update test imports.

**Commit:** `refactor(dhan): restructure flat files into organized subdirectories`

---

### PHASE 7: Cleanup & Documentation

> **Risk:** LOW-MEDIUM  
> **Agents:** Agent-α (deletions), Agent-δ (simplifications), Agent-ζ (validate)  
> **Duration:** 4–6 hours  
> **Depends on:** Phase 5 ✅  
> **Can parallelize with:** Phase 6

#### 7.1 Archive `poc/`

```bash
mkdir -p docs/poc
mv poc/* docs/poc/
rmdir poc/
```

#### 7.2 Categorize `scripts/`

```bash
mkdir -p scripts/{audit,debug,migration,verify}
# Sort 45 files into categories
```

#### 7.3 Simplify config profile hierarchy

Replace 3-class hierarchy with dataclass:
```python
@dataclass
class EnvironmentProfile:
    env: str = "dev"
    strict_validation: bool = False
    allow_mock_brokers: bool = True
    debug_endpoints: bool = True
```

#### 7.4 Fix pre-commit pytest-smoke hook paths

**Current (broken):** References `tests/brokers/*/tests/`  
**Correct:** References `brokers/*/tests/`

#### 7.5 Fix duplicate `contract` marker in pyproject.toml

Remove the duplicate entry.

#### 7.6 Add `api/` to coverage source

**Commit:** `chore(cleanup): archive poc, categorize scripts, fix CI hooks`

---

### PHASE 8: Update Import Linter Contracts

> **Risk:** MEDIUM — Contract changes  
> **Agents:** Agent-ζ (primary)  
> **Duration:** 2–4 hours  
> **Depends on:** Phase 5 ✅  

#### 8.1 Update root_packages

```toml
[tool.importlinter]
root_packages = ["domain", "application", "infrastructure", "brokers",
                 "analytics", "datalake", "api", "cli", "tradex"]
```

Remove `shared` (deleted), update `infrastructure` contracts.

#### 8.2 Simplify contracts

After all moves, most `ignore_imports` should be eliminated. The new contracts should be clean:

```toml
# Rule 1: Domain is independent
[[tool.importlinter.contracts]]
name = "Domain independence"
type = "forbidden"
source_modules = ["domain"]
forbidden_modules = ["application", "infrastructure", "brokers",
                     "analytics", "datalake", "cli", "api", "tradex"]

# Rule 2: Application depends only on domain
[[tool.importlinter.contracts]]
name = "Application depends only on domain"
type = "forbidden"
source_modules = ["application"]
forbidden_modules = ["infrastructure", "brokers", "analytics",
                     "datalake", "cli", "api"]

# Rule 3: Infrastructure depends only on domain
[[tool.importlinter.contracts]]
name = "Infrastructure depends only on domain"
type = "forbidden"
source_modules = ["infrastructure"]
forbidden_modules = ["application", "brokers", "analytics",
                     "datalake", "cli", "api"]

# Rule 4: Brokers depend only on domain
[[tool.importlinter.contracts]]
name = "Broker isolation"
type = "forbidden"
source_modules = ["brokers"]
forbidden_modules = ["application", "infrastructure", "analytics",
                     "datalake", "cli", "api"]

# Rule 5: Interface depends on application only
[[tool.importlinter.contracts]]
name = "Interface isolation"
type = "forbidden"
source_modules = ["api", "cli"]
forbidden_modules = ["infrastructure", "brokers", "analytics", "datalake"]
```

#### 8.3 Update architecture tests

```python
# tests/architecture/test_clean_architecture.py (NEW)
"""Verify Clean Architecture dependency directions."""
FORBIDDEN_IMPORTS = {
    "domain": ["application", "infrastructure", "brokers", "analytics",
               "datalake", "cli", "api", "tradex"],
    "application": ["infrastructure", "brokers", "analytics",
                    "datalake", "cli", "api"],
    "infrastructure": ["application", "brokers", "analytics",
                       "datalake", "cli", "api"],
    "brokers": ["application", "infrastructure", "analytics",
                "datalake", "cli", "api"],
}
```

**Commit:** `refactor(import-linter): update contracts for new architecture`

---

### PHASE 9: Update pyproject.toml & CI

> **Risk:** LOW  
> **Agents:** Agent-ζ (primary)  
> **Duration:** 2–4 hours  
> **Depends on:** Phase 8 ✅  

#### 9.1 Update setuptools packages

```toml
[tool.setuptools.packages.find]
where = ["src", "."]
include = ["brokers*", "cli*", "analytics*", "datalake*", "config*",
           "domain*", "application*", "infrastructure*", "tradex*"]
# Removed: providers*, interfaces*, shared*, plugins*, runtime*
```

#### 9.2 Update pytest testpaths

```toml
testpaths = ["tests", "brokers", "analytics", "cli", "datalake",
             "application", "src", "tradex"]
# Removed: infrastructure (absorbed), infrastructure tests move to tests/
```

#### 9.3 Update coverage source

```toml
[tool.coverage.run]
source = ["brokers", "analytics", "cli", "datalake", "application",
          "domain", "infrastructure", "api", "tradex"]
```

#### 9.4 Consolidate CI workflows

Remove `mutation_nightly.yml` if `mutation_testing.yml` covers the same scope.

#### 9.5 Update pre-commit hooks

Fix the pytest-smoke hook paths and ensure mypy covers more modules.

**Commit:** `chore(ci): update pyproject.toml, CI workflows, and pre-commit for new structure`

---

### PHASE 10: Final Validation & Documentation

> **Risk:** NONE  
> **Agents:** ALL  
> **Duration:** 4–6 hours  
> **Depends on:** Phase 9 ✅  

#### 10.1 Full regression suite

```bash
# Architecture fitness
PYTHONPATH="src:." pytest tests/architecture/ -v

# Import linter
PYTHONPATH="src:." lint-imports --config pyproject.toml

# Full test suite
PYTHONPATH="src:." pytest tests/ -x -q --timeout=120

# Coverage report
PYTHONPATH="src:." pytest tests/ \
  --cov=brokers --cov=analytics --cov=datalake \
  --cov=application --cov=domain --cov=infrastructure \
  --cov=api --cov=tradex \
  --cov-report=term-missing --cov-fail-under=80

# Ruff lint
ruff check .
ruff format --check .
```

#### 10.2 Update ARCHITECTURE.md

Document the final module structure, dependency rules, and layer responsibilities.

#### 10.3 Update README.md

Reflect new project structure and development workflow.

#### 10.4 Create PR

```bash
git push origin refactor/structural-cleanup
# Create PR with full description of changes
```

---

## 7. Dependency Graph

### Phase Dependencies

```
Phase 0 (Branch)
    │
    ▼
Phase 1 (Hygiene) ─────────────────────────────────────────────
    │                                                           │
    ▼                                                           │
Phase 2 (Facade + Moves)                                        │
    │                                                           │
    ├──────────────────┬────────────────────────────┐           │
    ▼                  ▼                            ▼           │
Phase 3            Phase 4                       Phase 6        │
(Duplicates)      (God Classes)              (Dhan Restructure) │
    │                  │                            │           │
    │                  ├────────────────────────────┘           │
    │                  ▼                                        │
    │              Phase 5                                      │
    │            (SOLID + Deps)                                 │
    │                  │                                        │
    │                  ├────────────────────────────────────────┘
    │                  │
    │                  ▼
    │              Phase 7 (Cleanup)
    │                  │
    │                  ▼
    │              Phase 8 (Import Linter)
    │                  │
    │                  ▼
    │              Phase 9 (CI + pyproject)
    │                  │
    │                  ▼
    │              Phase 10 (Final Validation)
    │                  │
    │                  ▼
    │          ┌───────────────┐
    └─────────►│  REGRESSION   │
               │    SUITE      │
               └───────────────┘
```

### Parallelization Opportunities

```
Week 1:  [α Phase 1] ──► [γ Phase 2]
Week 2:  [β Phase 3] [δ Phase 4a] [δ Phase 4b] [δ Phase 4c]  (PARALLEL)
Week 3:  [δ Phase 4d] [δ Phase 4e] [δ Phase 4f] [γ Phase 6]  (PARALLEL)
Week 4:  [γ Phase 5a] [δ Phase 5b] ──► [Phase 7] [Phase 8]
Week 5:  [ζ Phase 9] [Phase 10] ──► PR
Week 6:  Buffer
```

---

## 8. Multi-Agent Team Execution Model

### Agent Assignments

| Agent | Role | Phases | Focus |
|---|---|---|---|
| **Agent-α** | Delete & Clean | 1, 7 | Dead code, hygiene, archiving, pycache |
| **Agent-β** | Consolidate | 3, 5b | Duplicate merging, indicator consolidation, ISP fixes |
| **Agent-γ** | Restructure | 2, 5a, 6, 8 | Facade creation, dependency fixes, dhan restructure, linter |
| **Agent-δ** | Refactor | 4a-f, 5c, 7c | God class decomposition, SOLID fixes, simplification |
| **Agent-ε** | Test Repair | 4, 6 | Fix broken tests after moves, add decomposition tests |
| **Agent-ζ** | Guard | ALL | Architecture tests, import linter, regression gates, CI |

### Agent Communication Protocol

1. Each agent works on a **disjoint write set** (no two agents edit the same file)
2. After each phase, Agent-ζ runs the regression gate
3. If gate fails, the offending agent fixes before next phase starts
4. Agents communicate via the regression gate — no direct coordination needed

---

## 9. Regression Gate Protocol

### Per-Phase Gates (Non-Negotiable)

Every phase MUST pass its gate before the next phase begins.

| Gate | Command | When |
|---|---|---|
| **Architecture fitness** | `PYTHONPATH="src:." pytest tests/architecture/ -x -q` | After every phase |
| **Import linter** | `PYTHONPATH="src:." lint-imports --config pyproject.toml` | After every phase |
| **Module unit tests** | `PYTHONPATH="src:." pytest <affected_module>/tests/ -x -q` | After every phase |
| **Full regression** | `PYTHONPATH="src:." pytest tests/ -x -q --timeout=120` | End of each week |
| **Coverage gate** | `--cov-fail-under=80` | Final validation |

### Gate Failure Protocol

1. **Immediate revert:** `git revert HEAD`
2. **Root cause analysis:** What import broke? What test failed?
3. **Fix and re-run gate:** Only proceed after green
4. **Never skip a gate** — this is the safety net

---

## 10. Risk Mitigation & Rollback

### The Facade Pattern (Key Safety Net)

The `tradex.runtime` facade is the **single most important safety mechanism**:

1. **Phase 2:** Create facade — all 116 files become thin re-exports
2. **Phases 3-5:** Move code — facade re-exports from new locations
3. **Phase 8:** Add deprecation warnings to facade imports
4. **Future:** Remove facade after all consumers migrate

**If anything breaks:** Revert the specific move, the facade still works.

### Per-Phase Rollback

```bash
# Find the phase commit
git log --oneline
# Revert that specific phase
git revert <commit>
```

### Nuclear Rollback

```bash
# Back to before any cleanup
git checkout refactor/brokers-consolidation
```

### Risk Matrix

| Phase | Risk | Mitigation |
|---|---|---|
| Phase 1 (Hygiene) | LOW | Verified zero imports before deletion |
| Phase 2 (Facade) | LOW | Pure re-exports, no logic changes |
| Phase 3 (Duplicates) | MEDIUM | Diff before merge, full test suite |
| Phase 4 (God Classes) | HIGH | Composition pattern, preserve public API |
| Phase 5 (SOLID) | MEDIUM | Test-first, incremental |
| Phase 6 (Dhan) | MEDIUM | File moves only, update imports |
| Phase 7 (Cleanup) | LOW | Simple moves and deletions |
| Phase 8 (Contracts) | MEDIUM | Must pass lint-imports |
| Phase 9 (CI) | LOW | Config changes only |
| Phase 10 (Validation) | NONE | Read-only verification |

---

## 11. Appendices

### Appendix A: File Impact Summary

| Phase | Files Deleted | Files Modified | Files Created | Net Change |
|---|---|---|---|---|
| Phase 1 | ~35 | 2 (.gitignore) | 0 | -33 |
| Phase 2 | ~10 (shims) | ~116 (facades) | ~60 (canonical) | +44 |
| Phase 3 | ~8 (duplicates) | ~15 | 0 | -8 |
| Phase 4 | 0 | ~12 | ~15 (decomposed) | +15 |
| Phase 5 | 0 | ~20 | ~5 | +5 |
| Phase 6 | 0 | ~30 (moves) | 0 | 0 |
| Phase 7 | ~25 | ~10 | 0 | -25 |
| Phase 8 | 0 | ~5 | ~2 (new tests) | +2 |
| Phase 9 | ~2 (CI) | ~5 | 0 | -2 |
| Phase 10 | 0 | ~3 | 0 | 0 |
| **TOTAL** | **~80** | **~218** | **~82** | **+2** |

### Appendix B: Before/After Dependency Graph

**BEFORE (Dependency Web):**
```
                domain (230 files)
                  ↑
            tradex.runtime (116 files) ←── COUPLING HUB
           ↗    ↑    ↑    ↖
    application brokers api cli
        ↑         ↑
    infrastructure  config
```

**AFTER (Clean DAG):**
```
    domain (265 files — stable center)
      ↑
    application (110 files — orchestration)
      ↑
    infrastructure (162 files — implementations)
      ↑                    ↑
    brokers (422 files)   analytics (130 files)
      ↑                    ↑
    api (43 files)       datalake (90 files)
    cli (97 files)
```

### Appendix C: Import Linter Workaround Reduction

| Contract | Before | After | Resolved By |
|---|---|---|---|
| Domain independence | 0 | 0 | — |
| Infrastructure independence | 2 | 0 | Phase 2 (facade) |
| Analytics broker isolation | 0 | 0 | — |
| Broker common isolation | 5 | 2 (test-only) | Phase 5c (CLI abstraction) |
| Application broker isolation | 1 | 0 | Phase 5c |
| Application infrastructure separation | 11 | 0 | Phase 2-5 (proper layers) |
| CLI broker isolation | 8 | 2 (test-only) | Phase 5c (application registry) |
| Tradex public API broker isolation | 2 | 1 (paper session) | Acceptable |
| **TOTAL** | **30** | **5** | **83% reduction** |

### Appendix D: Key Principles Applied

| Principle | Application |
|---|---|
| **Dependency Rule** (Bob Martin) | All arrows point inward; domain has zero outward deps |
| **SRP** (Single Responsibility) | Each class has one reason to change |
| **OCP** (Open/Closed) | New brokers added via adapter pattern, not modifying core |
| **LSP** (Liskov Substitution) | All broker gateways implement same protocol |
| **ISP** (Interface Segregation) | CommonBrokerGateway split into 3 focused protocols |
| **DIP** (Dependency Inversion) | Application depends on domain ports, not concrete brokers |
| **DRY** | Single source of truth for indicators, scanners, circuit breaker |
| **YAGNI** | Delete providers/, interfaces/, shared/, plugins/ (not needed) |
| **Facades** | tradex.runtime becomes thin re-export layer (backward compat) |
| **Strangler Fig** | Gradual migration: facade first, move code, deprecate facade |
| **Boy Scout Rule** | Every phase leaves the code cleaner than it found it |
| **Red-Green-Refactor** | Test gates ensure no regression at any step |

---

*This plan is grounded in the actual codebase (1,100+ files, 642 test files, 227 pycache dirs, 30 import linter workarounds). Every finding has been validated against the source. Execute in order, pass every gate, and the result is a clean architecture with a dependency DAG instead of a web.*
