# Architecture Guardrails

> **Phase 1 — D1.9** | Auto-enforced invariants protecting architectural integrity.
> Every guardrail maps to a test in `tests/architecture/`. Breaking a guardrail
> means the architecture is regressing — fix the code, not the test.

---

## Table of Contents

1. [Existing Guardrails](#existing-guardrails)
2. [Proposed New Guardrails](#proposed-new-guardrails)
3. [Adding a New Guardrail](#adding-a-new-guardrail)

---

## Existing Guardrails

### G01 — Domain Layer Isolation

| Field | Value |
|-------|-------|
| **Enforces** | `src/domain/` must never import from `application`, `brokers`, `analytics`, `interface`, `config`, `infrastructure`, `datalake`, `plugins`, `tradex`, or `runtime` |
| **Test file** | `tests/architecture/test_domain_isolation.py` |
| **Mechanism** | AST walk over all `.py` files under `src/domain/`; extracts import root names and checks against forbidden layer list |
| **Scans** | `src/domain/**/*.py` (excludes `__pycache__`, `tests/`) |
| **Status** | ✅ Passing |

**How it works:** For each production Python file under `src/domain/`, the test parses the AST, extracts every `import` and `from ... import` statement, and checks if the top-level module name matches any of the 10 forbidden layers. An additional guard asserts the scanner found ≥20 files (preventing silent false-green from path drift).

---

### G02 — Domain Does Not Import `tradex`

| Field | Value |
|-------|-------|
| **Enforces** | Production domain modules must not import `tradex` (the composition root / runtime facade) |
| **Test file** | `tests/architecture/test_domain_no_tradex_imports.py` |
| **Mechanism** | AST walk over `src/domain/**/*.py`; checks for `tradex` as import root |
| **Scans** | `src/domain/**/*.py` (excludes `__pycache__`, `tests/`) |
| **Status** | ✅ Passing |

**How it works:** Dedicated test (superset of G01 for the `tradex` root specifically). Uses AST-based detection so comments and docstrings mentioning `tradex.connect` or `tradex.runtime.*` don't trigger false positives. Asserts scanner found ≥20 files.

---

### G03 — Domain Does Not Import `brokers`

| Field | Value |
|-------|-------|
| **Enforces** | Domain layer must not import any `brokers.*` package (TRANS-P3-010) |
| **Test file** | `tests/architecture/test_domain_no_broker_imports.py` |
| **Mechanism** | AST walk over `src/domain/**/*.py`; checks for `brokers` or `brokers.*` import prefixes |
| **Scans** | `src/domain/**/*.py` |
| **Status** | ✅ Passing |

---

### G04 — Domain Does Not Import `pandas` at Top Level

| Field | Value |
|-------|-------|
| **Enforces** | No top-level `import pandas` or `from pandas import ...` in domain production modules |
| **Test file** | `tests/architecture/test_domain_no_pandas_import.py` |
| **Mechanism** | AST walk: checks only top-level statements (not inside functions) for pandas imports. Also runs a cold-start import test: imports core domain modules with pandas absent from `sys.modules` and asserts it stays absent |
| **Scans** | `src/domain/**/*.py` (excludes `__pycache__`, `tests/`) |
| **Status** | ✅ Passing |

**How it works:** Two-phase check. Phase 1: AST scan of `tree.body` (top-level only) for pandas import statements. Phase 2: Removes pandas from `sys.modules`, imports 10 core domain modules, and asserts pandas was never loaded. Lazy imports inside functions (e.g., `to_dataframe`) are permitted.

---

### G05 — Import Direction and Layering

| Field | Value |
|-------|-------|
| **Enforces** | Multiple layering rules: (a) `brokers.common` must not import `brokers.dhan` or `brokers.upstox`, (b) `brokers.dhan` and `brokers.upstox` must not cross-import, (c) `datalake`/`analytics` must not import `cli`, (d) no imports from deleted `brokers.common` shim modules, (e) no imports from deprecated `brokers.common.event_bus` path |
| **Test file** | `tests/architecture/test_import_direction_and_layering.py` |
| **Mechanism** | AST walk + string pattern matching on import module paths |
| **Scans** | `brokers/common/`, `brokers/dhan/`, `brokers/upstox/`, `datalake/`, `analytics/`, and all production directories for shim violations |
| **Status** | ✅ Passing |

**How it works:** 7 test classes with distinct checks:
- `TestImportDirection`: 5 tests verifying broker isolation and no cli imports from datalake/analytics
- `TestModuleBoundaries`: 3 tests verifying `__all__` declarations and no broker-specific types in `brokers/__init__.py`
- `TestNamingConventions`: soft check for exception class naming
- `TestDocumentation`: soft check for module docstrings

---

### G06 — Gateway Surface Freeze

| Field | Value |
|-------|-------|
| **Enforces** | Public method sets on `DhanBrokerGateway`, `UpstoxBrokerGateway`, and `PaperGateway` are frozen. New methods require explicit PR review |
| **Test file** | `tests/architecture/test_gateway_surface_freeze.py` |
| **Mechanism** | Python introspection: `inspect.isfunction()` on `cls.__dict__` (class body methods only, not inherited) compared against frozen `frozenset` allowlists |
| **Scans** | `DhanBrokerGateway`, `UpstoxBrokerGateway`, `PaperGateway` class definitions |
| **Status** | ✅ Passing |

---

### G07 — Concurrency Boundary (Single Event Loop)

| Field | Value |
|-------|-------|
| **Enforces** | Exactly ONE module (`src/runtime/event_loop.py`) may call `asyncio.new_event_loop()`. All other call sites must use `run_coro_sync` / `get_runtime_loop` / `new_dedicated_loop` |
| **Test file** | `tests/architecture/test_concurrency_boundary.py` |
| **Mechanism** | `grep -rl` for `new_event_loop(` across `src/`; verifies only the sanctioned module contains it. Unit tests for `ensure_runtime_loop`, `get_runtime_loop`, `run_coro_sync`, `assert_single_loop_boundary` |
| **Scans** | `src/**/*.py` |
| **Status** | ✅ Passing |

---

### G08 — Fail-Closed Capital Paths

| Field | Value |
|-------|-------|
| **Enforces** | (a) OMS order lifecycle must attempt event publish on money paths, (b) EventBus handler failures must go to DLQ or be logged, (c) EventBus must expose managed service interface |
| **Test file** | `tests/architecture/test_fail_closed_capital_paths.py` |
| **Mechanism** | Source text assertions: checks for `_publish`/`publish`, `require_execution_ledger`/`ledger_authority`, `DeadLetterQueue`/`dead_letter`, `as_managed_service`, `EventBusAlertingService` in specific source files |
| **Scans** | `src/application/oms/_internal/order_lifecycle.py`, `src/infrastructure/event_bus/event_bus.py` |
| **Status** | ✅ Passing |

---

### G09 — No Broker Name Branching

| Field | Value |
|-------|-------|
| **Enforces** | OMS, certification suite, and rate limiter must never branch on concrete broker name strings (DR-B1/B2/B3). Dispatch must be capability-driven |
| **Test file** | `tests/architecture/test_no_broker_name_branching.py` |
| **Mechanism** | String literal search + regex pattern matching for `broker_id == "..."` / `broker == "..."` comparisons against 20+ live broker names |
| **Scans** | `src/application/oms/**/*.py`, `src/brokers/certification/suite.py`, `src/infrastructure/resilience/rate_limiter.py` |
| **Status** | ✅ Passing |

---

### G10 — No Security ID Leakage at Public Boundaries

| Field | Value |
|-------|-------|
| **Enforces** | Broker token fields (`security_id`, `instrument_token`, `securityId`, `Security ID`) must not appear in public-facing surfaces (interface, CLI, MCP, services) |
| **Test file** | `tests/architecture/test_no_security_id_leak.py` |
| **Mechanism** | Regex scan (`re.compile`) of all `.py` files under scan roots; allows lines with `ponytail:` or `# internal` comments |
| **Scans** | `src/interface/`, `src/brokers/mcp/`, `src/brokers/cli/`, `src/brokers/services/` |
| **Status** | ✅ Passing |

---

### G11 — Wire Boundary (Application/Domain Not Import Wire)

| Field | Value |
|-------|-------|
| **Enforces** | `application` and `domain` layers must not import broker wire modules (`brokers.dhan.wire`, `brokers.upstox.wire`, `brokers.dhan.api`, `brokers.upstox.api`) (ADR-021) |
| **Test file** | `tests/architecture/test_wire_boundary.py` |
| **Mechanism** | AST walk over `src/application/` and `src/domain/`; checks for forbidden import prefixes |
| **Scans** | `src/application/**/*.py`, `src/domain/**/*.py` |
| **Status** | ✅ Passing |

---

### G12 — Ledger Outbox Record-Then-Submit

| Field | Value |
|-------|-------|
| **Enforces** | Order lifecycle must use `persist_intent_then_submit` for the record-then-submit pattern (TRANS-P5-030). The outbox function must contain `record_intent` |
| **Test file** | `tests/architecture/test_ledger_outbox_boundary.py` |
| **Mechanism** | `inspect.getsource()` on `OrderLifecycle.submit_to_broker` and `ledger_outbox.persist_intent_then_submit`; asserts required string patterns exist in source |
| **Scans** | `src/application/oms/_internal/order_lifecycle.py`, `src/application/oms/ledger_outbox.py` |
| **Status** | ✅ Passing |

---

### G13 — Application Does Not Import Infrastructure

| Field | Value |
|-------|-------|
| **Enforces** | Application layer must not import `infrastructure.*` (TRANS-P3-011), except for approved debt edges listed in `_APPROVED_EDGES` |
| **Test file** | `tests/architecture/test_application_no_infra_imports.py` |
| **Mechanism** | AST walk over `src/application/**/*.py`; checks import targets against approved edges and forbidden targets (`infrastructure.observability.tracing`) |
| **Scans** | `src/application/**/*.py` (excludes test subdirectories) |
| **Status** | ✅ Passing |

---

### G14 — Domain Types Single Source of Truth

| Field | Value |
|-------|-------|
| **Enforces** | Canonical domain types (`Quote`, `Balance`, `DepthLevel`, `MarketDepth`, `Order`, `Position`, `OptionChain`) must be defined exactly once, in `domain/` |
| **Test file** | `tests/architecture/test_domain_single_source.py` |
| **Mechanism** | AST walk over `src/brokers/**/*.py` looking for `ClassDef` nodes matching canonical type names; asserts no definitions outside `domain/` |
| **Scans** | `src/brokers/**/*.py` |
| **Status** | ✅ Passing |

---

### G15 — No Scattered `_load_dotenv`

| Field | Value |
|-------|-------|
| **Enforces** | `_load_dotenv` must be defined in exactly one file: `brokers/common/env_loader.py` |
| **Test file** | `tests/architecture/test_no_scattered_dotenv.py` |
| **Mechanism** | AST walk over `src/brokers/**/*.py` looking for `FunctionDef` nodes with name `_load_dotenv` |
| **Scans** | `src/brokers/**/*.py` |
| **Status** | ✅ Passing |

---

### G16 — Value Object Purity

| Field | Value |
|-------|-------|
| **Enforces** | (a) Domain value objects must not call `datetime.now()` directly (use `ClockPort`), (b) `Money` is a single canonical type across `domain.primitives` and `domain.value_objects`, (c) `Order.price`/`Order.quantity` are `Money`/`Quantity` types |
| **Test file** | `tests/architecture/test_domain_value_object_purity.py` |
| **Mechanism** | String search for `datetime.now(` in VO files; identity comparison of Money type aliases; `__dataclass_fields__` inspection on Order |
| **Scans** | `src/domain/value_objects/**/*.py`, `src/domain/primitives/value_objects.py`, `src/domain/orders/` |
| **Status** | ✅ Passing |

---

### G17 — Single Composition Root

| Field | Value |
|-------|-------|
| **Enforces** | `runtime.factory.build` is the single composition root entry point (ADR-017). Ledger authority defaults to off |
| **Test file** | `tests/architecture/test_composition_root.py` |
| **Mechanism** | Import verification and `inspect.getsource()` assertions |
| **Scans** | `runtime.factory`, `runtime.ledger_policy` |
| **Status** | ✅ Passing |

---

### G18 — Domain Ports Forbid Tradex Imports

| Field | Value |
|-------|-------|
| **Enforces** | Domain broker adapter port must not import `tradex`; bridge event types must be in canonical `EventType` enum; `DomainEvent` payload must be immutable; `EventBus` warns on unknown event types; capability type is shared via `domain.capabilities.broker_capabilities` SSOT |
| **Test file** | `tests/architecture/test_domain_ports_forbid_tradex_imports.py` |
| **Mechanism** | AST walk on port file; runtime assertions on event types and capability re-exports |
| **Scans** | `src/domain/ports/broker_adapter.py` |
| **Status** | ✅ Passing |

---

### G19 — Stream→OMS Lock Discipline

| Field | Value |
|-------|-------|
| **Enforces** | `PositionManager` must hold `threading.RLock` around book mutations. `OrderManager` must hold a lock around order operations. `OrderLifecycle` book writes must be under a lock parameter (TOS-P5-011) |
| **Test file** | `tests/architecture/test_stream_oms_lock_discipline.py` |
| **Mechanism** | Source text assertions: checks for `threading.RLock`, `RLock()`, `with self._lock`, `_lock`, `with lock` in specific source files |
| **Scans** | `src/application/oms/position_manager.py`, `src/application/oms/order_manager.py`, `src/application/oms/_internal/order_lifecycle.py` |
| **Status** | ✅ Passing |

---

### G20 — Factory Migration (Compose Delegates to Factory)

| Field | Value |
|-------|-------|
| **Enforces** | `interface.ui.services.compose` build functions must delegate to `runtime.factory.build`, not construct `TradingRuntimeFactory` directly (TRANS-P5-022) |
| **Test file** | `tests/architecture/test_factory_migration.py` |
| **Mechanism** | `inspect.getsource()` on `compose.build_runtime` and `compose.build_for_api`; asserts `"build("` present and `"TradingRuntimeFactory("` absent |
| **Scans** | `src/interface/ui/services/compose.py` |
| **Status** | ✅ Passing |

---

### G21 — No Duplicate Error Hierarchies

| Field | Value |
|-------|-------|
| **Enforces** | `BrokerError` must be defined exactly once in `src/domain/errors.py`. `infrastructure.resilience.errors` is the canonical import root |
| **Test file** | `tests/architecture/test_no_duplicate_error_hierarchies.py` |
| **Mechanism** | AST walk over all production directories looking for `ClassDef` nodes with name `BrokerError`; identity check on imported classes |
| **Scans** | All `src/` production directories |
| **Status** | ✅ Passing |

---

### G22 — No `tradex.runtime` in Production

| Field | Value |
|-------|-------|
| **Enforces** | Production packages must not import `tradex.runtime` or `tradex.runtime.*` (the deprecated backward-compat facade) |
| **Test file** | `tests/architecture/test_no_tradex_runtime_in_production.py` |
| **Mechanism** | AST walk over 9 production package trees; checks for `tradex.runtime` as import root |
| **Scans** | `src/domain/`, `src/application/`, `src/infrastructure/`, `src/brokers/`, `src/interface/`, `src/config/`, `src/datalake/`, `src/analytics/`, `src/runtime/` |
| **Status** | ✅ Passing |

---

### G23 — Deepening Enforcement

| Field | Value |
|-------|-------|
| **Enforces** | (a) No inline exchange alias dicts outside approved adapter modules, (b) `dhan/domain.py` has no static canonical re-exports (except `IST_OFFSET`), (c) OrderManager documents orchestration contract, (d) API orders router uses OMS submit function, (e) Broker service exposes OMS transport submit, (f) No broker-specific constants in `domain/constants/`, (g) Market symbols fixture exists |
| **Test file** | `tests/architecture/test_deepening_enforcement.py` |
| **Mechanism** | AST walk + source text assertions + file existence checks |
| **Scans** | `src/brokers/`, `src/interface/ui/`, `src/datalake/`, `src/application/oms/`, `src/interface/api/`, `src/domain/constants/` |
| **Status** | ✅ Passing |

---

### G24 — OHLCV Bar Types SSOT

| Field | Value |
|-------|-------|
| **Enforces** | OHLCV bar shapes must use `domain.HistoricalBar` as SSOT (ADR-020). No parallel `Bar`, `Candle`, or `HistoricalCandle` class definitions except in API schemas. API Candle is wire-only with mapper referencing `HistoricalBar` |
| **Test file** | `tests/architecture/test_domain_bar_types.py` |
| **Mechanism** | AST class definition search + source text assertions on mapper and router files |
| **Scans** | `src/application/streaming/`, `src/analytics/replay/`, `src/interface/api/`, `src/domain/orders/`, `src/domain/` (HistoricalCandle search) |
| **Status** | ✅ Passing |

---

### G25 — Cert Path Unity

| Field | Value |
|-------|-------|
| **Enforces** | `run_verify`, `run_certify`, `run_doctor` must all be re-exported from `platform_ops` (same function). Frontends must not import `BrokerCertifier` directly |
| **Test file** | `tests/architecture/test_cert_path_unity.py` |
| **Mechanism** | Identity comparison (`is`) on re-exported functions; AST import check on frontend files |
| **Scans** | `src/brokers/platform_ops.py`, `src/brokers/services/core.py`, CLI/MCP/UI files |
| **Status** | ✅ Passing |

---

### G26 — Cross-Cutting Concerns

| Field | Value |
|-------|-------|
| **Enforces** | (a) No `logging.basicConfig()` in production, (b) No bare `except:` in brokers, (c) No token print in brokers, (d) All broker exceptions inherit from `BrokerError`, (e) All non-broker exceptions inherit from `TradeXV2Error`, (f) No `verify=False` in production, (g) No `pickle.load` in production, (h) No inline Upstox URLs, (i) No bare token logging, (j) Phase 8 invariants (simulate_event, reconciliation monkey-patch, OMS place_order calls live_actionable, BrokerService has live_actionable, broker has authenticator registered, compose module exists, event log replays order_placed, trade model supports cumulative_filled) |
| **Test file** | `tests/architecture/test_cross_cutting_concerns.py` |
| **Mechanism** | Regex + string pattern matching across production files |
| **Scans** | `src/brokers/`, `src/application/`, `src/infrastructure/`, `src/interface/`, `src/config/`, `src/datalake/`, `src/analytics/`, `src/runtime/`, `src/tradex/` |
| **Status** | ✅ Passing |

---

### G27 — Production Code Fitness Rules

| Field | Value |
|-------|-------|
| **Enforces** | (a) Business layers must use centralized logging (not direct `logging.getLogger`), (b) Business layers must not create threads directly, (c) Infrastructure must not define code in broker layer, (d) Infrastructure must not import business modules (with allowlist), (e) Brokers must not import other brokers, (f) `TradeXV2Error` defined exactly once, (g) No hardcoded credentials, (h) No manual retry loops (use `@retry` decorator) |
| **Test file** | `tests/architecture/test_production_code_fitness_rules.py` |
| **Mechanism** | AST walk + regex pattern matching + subprocess call to validation script |
| **Scans** | All `src/` production directories |
| **Status** | ✅ Passing |

---

### G28 — Public SDK Surface Invariants

| Field | Value |
|-------|-------|
| **Enforces** | (a) Broker gateways are importable, (b) `InstrumentState` is single-export, (c) Dead `OMSGatewayProxy` removed, (d) Paper session smoke test, (e) `OrderAck` strips transport fields, (f) Broker contract module loads |
| **Test file** | `tests/architecture/test_public_sdk_surface_invariants.py` |
| **Mechanism** | Import verification, attribute checks, file existence checks, runtime instantiation |
| **Scans** | `brokers.dhan.wire`, `brokers.upstox.wire`, `domain.instruments`, `domain.value_objects.state`, `application.oms`, `domain.entities.order`, `tradex`, `brokers.common.contracts` |
| **Status** | ✅ Passing |

---

### G29 — System Invariants (Dhan Identity)

| Field | Value |
|-------|-------|
| **Enforces** | `assert_dhan_identity()` validates `DhanInstrumentRef` shape; `assert_valid_security_id()` validates security ID format. Rejects None, strings, dicts, empty strings, non-digit strings, negative/zero IDs, invalid segments |
| **Test file** | `tests/architecture/test_system_invariants.py` |
| **Mechanism** | Parametric unit tests on validation functions |
| **Scans** | `brokers.dhan.exceptions`, `brokers.dhan.identity`, `brokers.dhan.resilience.invariants` |
| **Status** | ✅ Passing |

---

### G30 — OMS No Broker Name Branching

| Field | Value |
|-------|-------|
| **Enforces** | Parametric guard ensuring each concrete broker name is absent from OMS source (superset of G09) |
| **Test file** | `tests/architecture/test_oms_no_broker_name_branching.py` |
| **Mechanism** | Parametrized pytest: for each of 20+ broker names, asserts `"<name>"` and `'<name>'` are absent from OMS files |
| **Scans** | `src/application/oms/**/*.py` |
| **Status** | ✅ Passing |

---

### G31 — Domain No Pandas Import (Additional)

| Field | Value |
|-------|-------|
| **Enforces** | Domain modules must not import from `tradex` (additional check on domain module resolution) |
| **Test file** | `tests/architecture/test_domain_no_tradex_imports.py` |
| **Mechanism** | Same as G02 (duplicate enforcement for safety) |
| **Status** | ✅ Passing |

---

## Summary Matrix

| ID | Guardrail | Technique | Scope |
|----|-----------|-----------|-------|
| G01 | Domain isolation | AST walk | `src/domain/` |
| G02 | Domain no tradex | AST walk | `src/domain/` |
| G03 | Domain no brokers | AST walk | `src/domain/` |
| G04 | Domain no pandas top-level | AST walk + cold-start import | `src/domain/` |
| G05 | Import direction & layering | AST walk + string matching | `brokers/`, `datalake/`, `analytics/` |
| G06 | Gateway surface freeze | Python introspection | `DhanBrokerGateway`, `UpstoxBrokerGateway`, `PaperGateway` |
| G07 | Concurrency boundary | `grep` + unit tests | `src/` |
| G08 | Fail-closed capital paths | Source text assertions | OMS lifecycle, EventBus |
| G09 | No broker name branching | String/regex scan | OMS, cert suite, rate limiter |
| G10 | No security ID leak | Regex scan | interface, CLI, MCP, services |
| G11 | Wire boundary | AST walk | `src/application/`, `src/domain/` |
| G12 | Ledger outbox pattern | `inspect.getsource()` | OMS lifecycle, ledger outbox |
| G13 | App no infra imports | AST walk | `src/application/` |
| G14 | Domain types SSOT | AST class search | `src/brokers/` |
| G15 | No scattered dotenv | AST function search | `src/brokers/` |
| G16 | Value object purity | String search + identity check | `src/domain/value_objects/` |
| G17 | Single composition root | Import + source inspection | `runtime.factory`, `runtime.ledger_policy` |
| G18 | Domain ports no tradex | AST + runtime assertions | `src/domain/ports/` |
| G19 | Stream→OMS lock discipline | Source text assertions | `src/application/oms/` |
| G20 | Factory migration | `inspect.getsource()` | `interface.ui.services.compose` |
| G21 | No duplicate error hierarchies | AST class search | All `src/` |
| G22 | No tradex.runtime in prod | AST walk | 9 production packages |
| G23 | Deepening enforcement | AST + source + file checks | Brokers, UI, OMS, API |
| G24 | OHLCV bar types SSOT | AST class search + source text | Streaming, replay, API, domain |
| G25 | Cert path unity | Identity + AST import | platform_ops, CLI, MCP, UI |
| G26 | Cross-cutting concerns | Regex + string patterns | All production code |
| G27 | Production code fitness | AST + regex + subprocess | All production code |
| G28 | Public SDK surface | Import + attribute + runtime | SDK boundary |
| G29 | System invariants | Parametric unit tests | Dhan identity |
| G30 | OMS no broker names | Parametrized pytest | `src/application/oms/` |

---

## Proposed New Guardrails

The following guardrails should be added in Phase 2 to further strengthen architectural integrity.

### NG01 — Max File Size (400 LOC)

| Field | Value |
|-------|-------|
| **Enforces** | No production Python file exceeds 400 lines of code |
| **Suggested test** | `tests/architecture/test_file_size_limits.py` |
| **Mechanism** | `wc -l` on all `src/**/*.py` files; fail if > 600 LOC, warn if > 400 LOC |
| **Rationale** | Files > 400 LOC typically indicate god-class or mixed-responsibility anti-patterns. Enforces ADR-011 decomposition |
| **Priority** | High — directly supports ADR-011 |

### NG02 — No `PYTEST_CURRENT_TEST` in Production Code

| Field | Value |
|-------|-------|
| **Enforces** | `PYTEST_CURRENT_TEST` environment variable must not be read in production code (only in test code) |
| **Suggested test** | `tests/architecture/test_no_pytest_env_in_production.py` |
| **Mechanism** | AST walk + regex scan for `PYTEST_CURRENT_TEST` in `src/**/*.py` |
| **Rationale** | Production code should never depend on test runner state. This is a contamination leak that causes subtle bugs when tests are run in unexpected configurations |
| **Priority** | High — correctness invariant |

### NG03 — No `__import__("logging")` Anti-Pattern

| Field | Value |
|-------|-------|
| **Enforces** | `__import__("logging")` must not appear in production code |
| **Suggested test** | `tests/architecture/test_no_dynamic_import_logging.py` |
| **Mechanism** | Regex scan for `__import__.*logging` in `src/**/*.py` |
| **Rationale** | Dynamic `__import__("logging")` is an anti-pattern that bypasses module caching and makes import tracking impossible. Use `import logging` directly or the centralized `infrastructure.logging_config` |
| **Priority** | Medium — code quality |

### NG04 — Event File Size Limits

| Field | Value |
|-------|-------|
| **Enforces** | Event definition files (`domain/events/types.py` and successors) must not exceed 200 LOC |
| **Suggested test** | `tests/architecture/test_event_file_size.py` |
| **Mechanism** | `wc -l` on event definition files |
| **Rationale** | Large event type files indicate coupling between unrelated event contexts (see ADR-010). Keeping event files small enforces bounded context separation |
| **Priority** | Medium — supports ADR-010 decomposition |

### NG05 — Bounded Context Isolation

| Field | Value |
|-------|-------|
| **Enforces** | Intra-layer imports follow bounded context rules: `application.oms` must not import `application.streaming`; `application.streaming` must not import `application.oms` (except through domain events) |
| **Suggested test** | `tests/architecture/test_bounded_context_isolation.py` |
| **Mechanism** | AST walk with context-to-forbidden-imports mapping |
| **Rationale** | Layer isolation (G01, G13) is enforced but intra-layer isolation between bounded contexts is not. This prevents coupling between OMS, streaming, trading, scheduling, and data contexts |
| **Priority** | High — supports ADR-009 |

### NG06 — No `os.system()` in Production Code

| Field | Value |
|-------|-------|
| **Enforces** | `os.system()` must not be called in production code; use `subprocess.run()` instead |
| **Suggested test** | `tests/architecture/test_no_os_system.py` |
| **Mechanism** | AST scan for `os.system()` calls in `src/**/*.py` |
| **Rationale** | `os.system()` doesn't capture output, has shell injection risks, and can't be mocked for testing |
| **Priority** | Medium — security and testability |

### NG07 — No Bare `except:` Without Exception Type

| Field | Value |
|-------|-------|
| **Enforces** | Production code must not use bare `except:` clauses (must specify exception type) |
| **Suggested test** | `tests/architecture/test_no_bare_except.py` |
| **Mechanism** | AST walk looking for `ExceptHandler` with `type=None` in `src/**/*.py` |
| **Rationale** | Bare `except:` catches `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit`, masking critical errors. Already tested in brokers (G26) but not globally |
| **Priority** | Medium — error handling quality |

### NG08 — No Mutable Default Arguments in Domain

| Field | Value |
|-------|-------|
| **Enforces** | Domain dataclass `__init__` and function signatures must not use mutable default arguments (`[]`, `{}`, `set()`) |
| **Suggested test** | `tests/architecture/test_no_mutable_defaults.py` |
| **Mechanism** | AST walk looking for `ast.List`, `ast.Dict`, `ast.Set` in default positions of `FunctionDef.args.defaults` within `src/domain/` |
| **Rationale** | Mutable defaults are a classic Python footgun that causes shared state bugs across instances |
| **Priority** | Low — correctness hygiene |

---

## Adding a New Guardrail

1. **Write the test** in `tests/architecture/` following existing patterns:
   - AST-based for import analysis (preferred — avoids false positives from comments)
   - `inspect.getsource()` for source content assertions
   - Regex/string for simple pattern matching
2. **Run the test** to confirm it passes (or documents a known failure for debt items)
3. **Update this document** with the new entry
4. **Tag the test** with `@pytest.mark.architecture` for CI filtering
5. **Add to CI** the `tests/architecture/` directory as a required gate

### Test Design Principles

- **Fail loudly on empty scans.** If your scanner finds zero files, the path has drifted — assert `len(files) >= N`.
- **Exclude tests and `__pycache__`.** Architecture tests should only scan production code.
- **Prefer AST over regex** for import analysis — regex matches comments and strings; AST matches real imports.
- **Use `inspect.getsource()`** when you need to verify function body content (e.g., that a function calls another function).
- **Parametrize** when checking the same rule across multiple inputs (e.g., multiple broker names).
