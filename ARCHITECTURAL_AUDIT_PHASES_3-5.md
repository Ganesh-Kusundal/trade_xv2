# Architectural Audit Report: Phases 3-5

## PHASE 3 - Root Cause Classification

All Phase 2 findings are grouped into six root cause categories below. Each finding is tagged with its Phase 2 reference code.

---

### RC-1: Missing Shared Vocabulary Layer

> The codebase lacks a single, canonical set of domain types, enums, and value objects. Parallel definitions coexist across layers, forcing ad-hoc aliases and conversion helpers.

| Finding | Evidence | Impact |
|---------|----------|--------|
| **F1 - Dual OrderIntent** | `domain/orders/intent.py` (pre-risk) vs `domain/execution_contracts.py` (durable/persisted). Comment acknowledges "Distinct from pre-risk domain.orders.intent.OrderIntent". | Consumers cannot know which OrderIntent a function expects without reading the source. |
| **F2 - Triple TradingSession** | (a) `domain/market/exchange.py` TradingSession NamedTuple (name, open_time, close_time), (b) `domain/sessions/trading_session.py` TradingSession dataclass with SessionStatus enum, (c) `analytics/replay/models.py` ReplaySession. Three unrelated types with overlapping names. | Name collision forces verbose qualified imports; new developers pick the wrong one. |
| **F3 - Dual SessionStatus** | `domain/session_status.py` SessionStatus dataclass (connect-time readiness) vs `domain/sessions/trading_session.py` SessionStatus enum (PENDING/ACTIVE/PAUSED/ENDED). | Same name, different semantics; runtime imports are ambiguous. |
| **F4 - Dual TimeService** | `infrastructure/time_service.py` (canonical per docstring) vs `runtime/time_service.py` (SystemClock/FakeClock variant). Two clock implementations (FakeClock in both files). | Violates single-source-of-truth; tests may mock the wrong one. |
| **F5 - Multiple MarketDataProvider Protocols** | `analytics/core/providers.py` MarketDataProvider vs `brokers/common/api/__init__.py` MarketDataProvider (deprecated). Parallel MarginProvider protocols. | Broker layer and analytics layer define overlapping contracts independently. |
| **F6 - Parallel Simulation Models** | `analytics/replay/models.py` (SimulatedTrade, SimulatedPosition, ReplayConfig) vs `analytics/paper/models.py` (PaperTrade, PaperPosition, PaperConfig). ~1000 lines of near-identical dataclasses. | Violates zero-parity rule; bug fixes must be applied twice. |
| **F7 - Parallel Signal Processors** | `analytics/replay/signal_processor.py` SignalProcessor (~308 lines) vs `analytics/paper/signal_processor.py` PaperSignalProcessor (~315 lines). Near-identical logic. | Code duplication; divergent behavior risk. |
| **F8 - Parallel Position Closers** | `analytics/replay/position_closer.py` PositionCloser (~227 lines) vs `analytics/paper/position_closer.py` PaperPositionCloser (~215 lines). Near-identical logic. | Code duplication; divergent behavior risk. |
| **F9 - PositionSide enum not elevated** | `PositionSide` enum exists only in `analytics/paper/models.py`. Not in `domain/enums.py` or `domain/market_enums.py`. | Domain layer cannot express position direction; analytics owns a domain concept. |
| **F10 - Analytics trade types duplicated** | `analytics/shared/trade_types.py` SimTrade/SimPosition with `sim_trade_to_domain()` converter. Parallel to both replay and paper models. | Third copy of simulation trade/position types. |
| **F11 - CandidateDTO/SignalDTO parallel to analytics** | `domain/models/trading.py` CandidateDTO/SignalDTO mirror `analytics/scanner/models.py` Candidate/Signal and `analytics/strategy/models.py` Signal/StrategyResult. | Domain layer contains DTOs that shadow analytics types instead of owning the canonical definition. |

---

### RC-2: Missing Service/Use-Case Layer

> Business logic that should live in a dedicated application service or use-case module is scattered across analytics, infrastructure, and broker layers.

| Finding | Evidence | Impact |
|---------|----------|--------|
| **F12 - Trading costs in domain** | `domain/trading_costs.py` (243 lines) contains CommissionModel, SlippageModel enums, IndianMarketFees dataclass. Consolidated from 6 previously duplicated locations, but still lives in domain instead of an application service. | Domain layer contains fee-calculation logic that is really an application concern. |
| **F13 - Fill pipeline in domain** | `domain/simulation_fill_pipeline.py` SimulationFillPipeline. Shared fill path for replay/paper lives in domain but is really an application-level orchestration concern. | Domain layer reaches into simulation orchestration. |
| **F14 - Portfolio projection in domain** | `domain/portfolio_projection.py` PortfolioProjector, project_trade(). Shared position book logic. | Domain contains what should be an application service that uses domain entities. |
| **F15 - Reconciliation engine in domain** | `domain/reconciliation_engine.py` ReconciliationEngine. Shared comparison logic. | Domain contains orchestration logic; should be an application service consuming domain ports. |
| **F16 - Mutable global resolver** | `application/ports.py` (48 lines) mutable global resolver pattern for execution target wiring. | Application layer uses global mutable state instead of explicit dependency injection through a composition root. |
| **F17 - Config duplication across layers** | `config/schema.py` AppConfig (Pydantic) vs `interface/api/config.py` APIConfig (dataclass) with overlapping fields (host, port, cors_origins, rate_limit). 35 Config classes across 25 files. | No single configuration authority; API layer re-declares fields from central config. |

---

### RC-3: Missing Domain Model

> Core domain concepts are either missing entirely, expressed as primitives, or buried in infrastructure/analytics code.

| Finding | Evidence | Impact |
|---------|----------|--------|
| **F18 - No Money/Quantity value objects enforced** | `domain/entities/order.py` uses Money/Quantity fields, but analytics code (`analytics/paper/models.py`, `analytics/replay/models.py`, `analytics/backtest/fast_backtest.py`) uses raw `float` and `Decimal(str(price))` without wrapping in value objects. | Type safety is bypassed; analytics code can mix currencies or pass raw floats where domain expects value objects. |
| **F19 - dict[str, Any] pervasive** | 50+ occurrences of `dict[str, Any]` across analytics (replay, walk-forward, core), runtime, domain (extensions, backtest, connect_errors). Typed models exist but are bypassed. | Loss of type safety; no compile-time validation of data shapes. |
| **F20 - No domain-level Instrument aggregate** | Instrument concepts scattered across `domain/instruments.py`, `application/services/instrument_registry.py` (CanonicalInstrument), broker-specific instrument mappers. No unified Instrument aggregate root. | Each layer constructs its own instrument representation. |
| **F21 - Exception hierarchy split** | Root exceptions in `domain/exceptions.py` (TradeXV2Error, ConfigError, ValidationError, etc.) vs broker errors in `domain/errors.py` (BrokerError, RetryableError, etc.). Infrastructure re-exports back from domain (`infrastructure/resilience/errors.py`). | Two parallel hierarchies under the same root; unclear where to catch; reversed dependency direction in infrastructure re-exports. |
| **F22 - No domain event bus contract enforced** | `domain/ports/event_publisher.py` defines EventBusPort protocol, but no evidence of a domain-events pattern being used consistently. Events are ad-hoc. | Domain events are not a first-class concept; consumers cannot rely on event-driven architecture. |

---

### RC-4: Boundary Violations

> Layer boundaries defined in import-linter contracts are violated or circumvented through workarounds.

| Finding | Evidence | Impact |
|---------|----------|--------|
| **F23 - Infrastructure re-exports to domain** | `infrastructure/resilience/errors.py` re-exports from `domain.errors` with comment "reversed dependency direction noted as backward compat". | Infrastructure reaching into domain error definitions and re-exporting them creates a circular dependency smell. |
| **F24 - Hardcoded "NSE" default (30+ occurrences)** | `"NSE"` appears as default parameter in: `analytics/core/providers.py` (5x), `analytics/paper/signal_processor.py` (8x), `analytics/paper/position_closer.py` (2x), `analytics/paper/models.py` (5x), `analytics/backtest/fast_backtest.py` (3x), `analytics/scanner/models.py` (2x), `application/services/instrument_registry.py` (4x), `application/services/download_engine.py` (1x), `config/endpoints.py` (1x), `config/indices.py` (2x), `tradex/session.py` (1x), `application/scheduling/quota_decorator.py` (1x), `application/options/capability.py` (1x). | Analytics/application layers hardcode broker-specific exchange defaults instead of using domain.Exchange enum or requiring explicit exchange parameter. |
| **F25 - String "BUY"/"SELL" instead of Side enum** | `analytics/paper/signal_processor.py` uses `"BUY"`, `"SELL"` strings (8+ occurrences). `analytics/paper/position_closer.py` uses `"SELL"`, `"BUY"` strings. `analytics/backtest/fast_backtest.py` uses `"BUY"`, `"SELL"` strings. `analytics/strategy/models.py` defines its own SignalType enum with BUY/SELL values. | Bypasses `domain.enums.Side` enum; stringly-typed code defeats type checking. |
| **F26 - Broker __getattr__ reach-through** | `brokers/dhan/domain.py` (365 lines) uses `__getattr__` for canonical re-exports. Code standards explicitly forbid getattr reach-throughs. | Hides import structure; IDE navigation breaks; violates project's own code standards. |
| **F27 - Status mapper side-effect at import** | `brokers/dhan/status_mapper.py` registers with StatusMapperRegistry at import time. Importing a module has side effects. | Importing a file changes global state; test isolation is compromised. |
| **F28 - domain/__init__.py mega-facade** | `domain/__init__.py` (146 lines) re-exports from 14+ submodules. Acts as a catch-all facade. | Encourages `from domain import X` without making the submodule dependency explicit; hides the internal structure. |
| **F29 - domain/types.py secondary facade** | `domain/types.py` (44 lines) re-exports from domain.enums, domain.market_enums, domain.capabilities, domain.entities.position, domain.entities.order_lifecycle. | Second level of indirection; consumers cannot tell which submodule owns a type. |

---

### RC-5: Premature File Splitting

> Files have been split into sub-modules without a clear ownership model, creating re-export chains and scattering related constants.

| Finding | Evidence | Impact |
|---------|----------|--------|
| **F30 - domain/constants/ over-split** | `domain/constants/__init__.py` (256 lines) re-exports from 9 submodules (auth, defaults, exchanges, market, observability, resilience, risk, segments, timeouts) but still contains OMS/reconciliation constants not yet split. | Incomplete split; __init__.py is both a facade and a dumping ground. |
| **F31 - domain/ split into too many single-concept files** | `domain/session_status.py`, `domain/reconciliation.py`, `domain/reconciliation_engine.py`, `domain/simulation_fill_pipeline.py`, `domain/simulation_position_meta.py`, `domain/portfolio_projection.py`, `domain/trading_costs.py`, `domain/execution_contracts.py` are all small files (29-243 lines) at the domain root. | Domain root is flat with many small files; no clear aggregation into sub-packages. |
| **F32 - domain/__init__.py + domain/types.py dual facade** | Two separate re-export facades for overlapping sets of domain types. | Consumers face ambiguity: import from `domain` or `domain.types`? |
| **F33 - Exception files split across domain** | `domain/exceptions.py` (70 lines, root exceptions) and `domain/errors.py` (213 lines, broker errors) are separate files at domain root, plus `infrastructure/resilience/errors.py` re-exports. | Three files for one exception hierarchy; unclear which to import from. |

---

### RC-6: Absent/Inconsistent Coding Standards

> Existing coding standards (documented in `context/code-standards.md`) are not uniformly enforced. Import patterns vary, aliases proliferate, and guardrails have gaps.

| Finding | Evidence | Impact |
|---------|----------|--------|
| **F34 - Import path inconsistency** | Three import styles coexist: `from domain import Side`, `from domain.types import Side`, `from domain.enums import Side`. No enforced canonical path. | Same type imported three different ways across the codebase. |
| **F35 - Type aliases obscure origin** | `OrderSide = Side` (analytics/paper/models.py), `DomainSide = Side` (various). Aliases make it unclear which is the canonical type. | IDE navigation breaks; grep for `Side` returns false positives. |
| **F36 - mypy only in ERROR mode on clean modules** | `.pre-commit-config.yaml` runs mypy with ERROR-mode gate only on modules that are already clean. Modules with existing type errors are excluded. | Type errors in non-clean modules are never caught; no path to full coverage. |
| **F37 - No banned-import rules for analytics** | `pyproject.toml` ruff banned-api rules cover broker/domain boundaries but do not prevent analytics layers from importing concrete broker types or hardcoding exchange strings. | Analytics layer drifts from domain vocabulary without CI detection. |
| **F38 - File LOC limit (ADR-011) not enforced on existing files** | `check-file-loc` pre-commit hook exists but many existing files exceed the limit (e.g., `analytics/replay/models.py` at 497 lines, `analytics/paper/models.py` at 499 lines, `brokers/dhan/domain.py` at 365 lines). | Grandfathered-in oversized files; new files are constrained but old ones grow unchecked. |
| **F39 - No contract preventing analytics/paper and analytics/replay duplication** | Import-linter contracts enforce layer boundaries (domain independence, broker isolation) but no contract prevents two modules within analytics from duplicating each other. | Structural duplication within analytics goes undetected by CI. |

---

## PHASE 4 - Refactoring Plan

Tasks are sequenced by dependency. Earlier tasks unblock later ones. Each task traces to its root cause and Phase 2 findings.

---

### REF-1: Unify Exception Hierarchy

| Field | Value |
|-------|-------|
| **Root Cause** | RC-3 (Missing Domain Model) |
| **Findings** | F21, F23, F33 |
| **Action** | Merge `domain/exceptions.py` and `domain/errors.py` into a single `domain/exceptions.py` with a clear two-tier hierarchy: (1) platform errors (TradeXV2Error subtree), (2) broker errors (BrokerError subtree). Remove `infrastructure/resilience/errors.py` re-exports; consumers import from `domain.exceptions` directly. |
| **From** | `domain/exceptions.py`, `domain/errors.py`, `infrastructure/resilience/errors.py` |
| **To** | `domain/exceptions.py` (single file, unified hierarchy) |
| **Touches** | `domain/__init__.py`, `domain/errors.py` (becomes thin re-export for backward compat, then removed), `infrastructure/resilience/errors.py` (deleted), all files importing from `domain.errors` |
| **Test Strategy** | Unit tests for exception hierarchy (isinstance checks, inheritance chain). Grep-based test to verify no direct imports from `domain.errors` after migration. Import-linter contract to prevent infrastructure from re-exporting domain errors. |
| **Sequencing Note** | Must complete before REF-9 (import standardization) because exception import paths are part of the canonical vocabulary. |

---

### REF-2: Elevate PositionSide to Domain Enums

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F9, F25 |
| **Action** | Move `PositionSide` enum from `analytics/paper/models.py` to `domain/enums.py` alongside `Side`. Replace all string `"BUY"`/`"SELL"` usage in analytics with `Side.BUY`/`Side.SELL`. Replace all string `"LONG"`/`"SHORT"` with `PositionSide.LONG`/`PositionSide.SHORT`. |
| **From** | `analytics/paper/models.py` (PositionSide), string literals across analytics/ |
| **To** | `domain/enums.py` (PositionSide), typed usage everywhere |
| **Touches** | `domain/enums.py`, `analytics/paper/models.py`, `analytics/paper/signal_processor.py`, `analytics/paper/position_closer.py`, `analytics/replay/signal_processor.py`, `analytics/replay/position_closer.py`, `analytics/backtest/fast_backtest.py`, `analytics/strategy/models.py` |
| **Test Strategy** | mypy strict pass after changes. Unit tests for signal processors using enum values. Ruff rule banning string literals `"BUY"`/`"SELL"` in analytics/. |
| **Sequencing Note** | Depends on REF-1 only for clean imports. Should complete before REF-5 (simulation model consolidation) because the consolidated models need typed fields. |

---

### REF-3: Eliminate Hardcoded "NSE" Defaults

| Field | Value |
|-------|-------|
| **Root Cause** | RC-4 (Boundary Violations) |
| **Findings** | F24 |
| **Action** | Replace all `exchange: str = "NSE"` defaults with `exchange: Exchange = Exchange.NSE` using the domain enum. In analytics providers, require explicit exchange parameter (no default). In application services, use the enum default. Add a ruff banned-api rule flagging `"NSE"` string literal as a default parameter value. |
| **From** | 30+ locations across analytics/, application/, config/, tradex/ |
| **To** | `domain/market_enums.py` Exchange enum used as default everywhere |
| **Touches** | `analytics/core/providers.py`, `analytics/paper/signal_processor.py`, `analytics/paper/position_closer.py`, `analytics/paper/models.py`, `analytics/backtest/fast_backtest.py`, `analytics/scanner/models.py`, `analytics/replay/parity_risk.py`, `application/services/instrument_registry.py`, `application/services/download_engine.py`, `application/scheduling/quota_decorator.py`, `application/options/capability.py`, `config/endpoints.py`, `tradex/session.py` |
| **Test Strategy** | Ruff custom check or banned-api rule for `"NSE"` string literal in function signatures. Integration tests for instrument resolution with explicit exchange. |
| **Sequencing Note** | Independent of REF-1/REF-2 but should complete before REF-9 (import standards). |

---

### REF-4: Consolidate OrderIntent Types

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F1 |
| **Action** | Rename `domain/orders/intent.py:OrderIntent` to `OrderCommand` (pre-risk, ephemeral). Keep `domain/execution_contracts.py:OrderIntent` as the durable/persisted intent. Add a clear docstring to each explaining the lifecycle stage. Update all references. |
| **From** | `domain/orders/intent.py` (OrderIntent) |
| **To** | `domain/orders/intent.py` (OrderCommand), `domain/execution_contracts.py` (OrderIntent, unchanged) |
| **Touches** | `domain/orders/intent.py`, `domain/orders/__init__.py`, all consumers of pre-risk OrderIntent |
| **Test Strategy** | mypy pass. Rename is a compile-time safe operation verified by type checker. Unit tests for order pipeline using both types. |
| **Sequencing Note** | Should complete before REF-5 because simulation models reference order intents. |

---

### REF-5: Consolidate Simulation Models (Paper/Replay)

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F6, F7, F8, F10 |
| **Action** | Create `analytics/simulation/` sub-package with shared base classes: (a) `models.py` - unified SimTrade, SimPosition, SimSession dataclasses parameterized by mode (paper/replay), (b) `signal_processor.py` - single SignalProcessor class used by both paper and replay, (c) `position_closer.py` - single PositionCloser class. Paper and replay modules become thin adapters that configure the shared classes. Remove `analytics/shared/trade_types.py` (absorbed into shared models). |
| **From** | `analytics/paper/models.py` (PaperTrade, PaperPosition, PaperSession), `analytics/paper/signal_processor.py`, `analytics/paper/position_closer.py`, `analytics/replay/models.py` (SimulatedTrade, SimulatedPosition, ReplaySession), `analytics/replay/signal_processor.py`, `analytics/replay/position_closer.py`, `analytics/shared/trade_types.py` |
| **To** | `analytics/simulation/models.py`, `analytics/simulation/signal_processor.py`, `analytics/simulation/position_closer.py`, `analytics/paper/` (thin adapter), `analytics/replay/` (thin adapter) |
| **Touches** | ~10 files in analytics/paper/ and analytics/replay/, `analytics/shared/trade_types.py` (deleted), `domain/simulation_fill_pipeline.py`, `domain/simulation_position_meta.py` |
| **Test Strategy** | Golden dataset parity tests (existing `analytics/replay/golden_dataset.py`). Property-based tests verifying paper and replay produce identical results for identical inputs. Import-linter contract preventing analytics/paper from importing analytics/replay internals (enforced via shared layer). |
| **Sequencing Note** | Depends on REF-2 (PositionSide elevation), REF-4 (OrderIntent consolidation). This is the highest-effort task; allocate dedicated sprint. |

---

### REF-6: Rename Conflicting Session/TradingSession Types

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F2, F3 |
| **Action** | (a) Rename `domain/market/exchange.py:TradingSession` to `MarketHours` (it represents exchange trading hours). (b) Rename `domain/session_status.py:SessionStatus` to `ConnectivityStatus` (it represents connect-time readiness). (c) Keep `domain/sessions/trading_session.py:TradingSession` and `SessionStatus` as the canonical session types. |
| **From** | `domain/market/exchange.py` (TradingSession NamedTuple), `domain/session_status.py` (SessionStatus dataclass) |
| **To** | `domain/market/exchange.py` (MarketHours NamedTuple), `domain/session_status.py` (ConnectivityStatus dataclass) |
| **Touches** | `domain/market/exchange.py`, `domain/session_status.py`, `domain/__init__.py`, all consumers |
| **Test Strategy** | mypy pass after rename. Grep-based test to verify no remaining references to old names. |
| **Sequencing Note** | Independent of REF-1 through REF-5. Can proceed in parallel. |

---

### REF-7: Unify TimeService

| Field | Value |
|-------|-------|
| **Root Cause** | RC-1 (Missing Shared Vocabulary Layer) |
| **Findings** | F4 |
| **Action** | Merge `runtime/time_service.py` clock implementations (SystemClock, FakeClock) into `infrastructure/time_service.py`. The infrastructure version becomes the single TimeService. Runtime imports TimeService from infrastructure via composition root wiring. Remove duplicate FakeClock. |
| **From** | `runtime/time_service.py` (SystemClock, FakeClock, TimeService), `infrastructure/time_service.py` (TimeService) |
| **To** | `infrastructure/time_service.py` (single TimeService with SystemClock/FakeClock), `runtime/` imports from infrastructure via DI |
| **Touches** | `runtime/time_service.py` (deleted or becomes thin re-export), `infrastructure/time_service.py`, `runtime/composition.py`, all test files using FakeClock |
| **Test Strategy** | Unit tests for TimeService with both clock implementations. Verify no duplicate clock definitions via grep-based test. |
| **Sequencing Note** | Independent of REF-1 through REF-6. Can proceed in parallel. |

---

### REF-8: Consolidate Config Classes

| Field | Value |
|-------|-------|
| **Root Cause** | RC-2 (Missing Service/Use-Case Layer) |
| **Findings** | F17 |
| **Action** | (a) Merge `interface/api/config.py:APIConfig` fields into `config/schema.py:AppConfig` under an `api` nested section. (b) Audit all 35 Config dataclasses; move orchestration configs to `application/`, infrastructure configs to `infrastructure/`, analytics configs to `analytics/`. (c) `AppConfig` becomes the single root; layer-specific configs are composed into it. |
| **From** | `interface/api/config.py` (APIConfig), 35 scattered Config dataclasses |
| **To** | `config/schema.py` (AppConfig as single root), layer-specific configs composed via AppConfig fields |
| **Touches** | `config/schema.py`, `interface/api/config.py` (deleted), `interface/api/` consumers, all Config class definitions |
| **Test Strategy** | Config validation tests (Pydantic model validation). Integration test verifying API starts with AppConfig-only configuration. |
| **Sequencing Note** | Independent of domain-layer refactorings. Can proceed in parallel with REF-1 through REF-7. |

---

### REF-9: Establish Canonical Import Paths

| Field | Value |
|-------|-------|
| **Root Cause** | RC-6 (Absent/Inconsistent Coding Standards) |
| **Findings** | F34, F35, F28, F29, F32 |
| **Action** | (a) Define canonical import paths for all domain types in `context/code-standards.md`. Rule: always import from the owning submodule (e.g., `from domain.enums import Side`), never from `domain` or `domain.types` facades. (b) Deprecate and eventually remove `domain/__init__.py` mega-facade and `domain/types.py` secondary facade. (c) Remove all type aliases (`OrderSide`, `DomainSide`). (d) Add ruff rules banning `from domain import Side` pattern (wildcard facade imports). |
| **From** | `domain/__init__.py` (146-line facade), `domain/types.py` (44-line facade), alias definitions across codebase |
| **To** | Direct submodule imports everywhere; facades deleted |
| **Touches** | `domain/__init__.py`, `domain/types.py`, every file using facade imports or aliases (~100+ files) |
| **Test Strategy** | Ruff custom rule or import-linter contract enforcing direct submodule imports. mypy strict pass. Grep test for banned alias names. |
| **Sequencing Note** | Must complete AFTER REF-1 (exception hierarchy), REF-2 (PositionSide), REF-4 (OrderIntent rename), REF-6 (session renames) because those change what the canonical paths are. This is the "lock it in" task. |

---

### REF-10: Move Orchestration Logic Out of Domain

| Field | Value |
|-------|-------|
| **Root Cause** | RC-2 (Missing Service/Use-Case Layer) |
| **Findings** | F12, F13, F14, F15 |
| **Action** | Create `application/services/` use-case modules: (a) `trading_costs_service.py` wrapping fee calculations, (b) `simulation_orchestrator.py` wrapping fill pipeline + position meta + portfolio projection, (c) `reconciliation_service.py` wrapping reconciliation engine. Domain retains pure entities/value objects; application layer owns orchestration. |
| **From** | `domain/trading_costs.py`, `domain/simulation_fill_pipeline.py`, `domain/simulation_position_meta.py`, `domain/portfolio_projection.py`, `domain/reconciliation_engine.py` |
| **To** | `application/services/trading_costs_service.py`, `application/services/simulation_orchestrator.py`, `application/services/reconciliation_service.py`. Domain files become pure data (entities, value objects) or are deleted if fully absorbed. |
| **Touches** | 5 domain files (moved/simplified), `application/services/` (new files), `domain/__init__.py`, all consumers |
| **Test Strategy** | Unit tests for each service. Integration tests verifying domain layer has no orchestration logic (import-linter: domain must not import from application). |
| **Sequencing Note** | Depends on REF-5 (simulation model consolidation) because the simulation orchestrator wraps the consolidated models. |

---

### REF-11: Eliminate dict[str, Any] in Favor of Typed Models

| Field | Value |
|-------|-------|
| **Root Cause** | RC-3 (Missing Domain Model) |
| **Findings** | F19 |
| **Action** | (a) Audit all `dict[str, Any]` usage; replace with typed dataclasses or Pydantic models where the shape is known. (b) For `analytics/replay/models.py` fields like `bar_data: dict[str, Any]`, define `BarData` dataclass. (c) For `domain/extensions/` payload dicts, define typed payload models per extension capability. (d) Add mypy strict mode to modules that have been cleaned. |
| **From** | 50+ locations with `dict[str, Any]` |
| **To** | Typed dataclasses/Pydantic models |
| **Touches** | `analytics/replay/models.py`, `analytics/core/models.py`, `analytics/walk_forward/engine.py`, `domain/extensions/`, `domain/backtest/models.py`, `domain/connect_errors.py`, `runtime/` files |
| **Test Strategy** | mypy strict pass on cleaned modules. Unit tests for new typed models. Gradual rollout: clean one module at a time, enable mypy strict per-module. |
| **Sequencing Note** | Large effort; should be done incrementally after REF-1 through REF-5 stabilize the type landscape. |

---

### REF-12: Remove Broker __getattr__ Reach-Throughs

| Field | Value |
|-------|-------|
| **Root Cause** | RC-4 (Boundary Violations) |
| **Findings** | F26 |
| **Action** | Replace `__getattr__` re-export pattern in `brokers/dhan/domain.py` with explicit imports. Each consumer imports directly from the defining submodule. |
| **From** | `brokers/dhan/domain.py` (__getattr__ pattern) |
| **To** | Explicit imports from defining submodules |
| **Touches** | `brokers/dhan/domain.py`, all consumers of dhan domain types |
| **Test Strategy** | Ruff rule banning `__getattr__` for re-exports. Import-linter contract for broker internal boundaries. |
| **Sequencing Note** | Independent; can proceed at any time. |

---

### REF-13: Flatten Domain Constants Package

| Field | Value |
|-------|-------|
| **Root Cause** | RC-5 (Premature File Splitting) |
| **Findings** | F30, F31 |
| **Action** | (a) Move remaining OMS/reconciliation constants from `domain/constants/__init__.py` into appropriate submodules (e.g., `domain/constants/oms.py`). (b) Make `domain/constants/__init__.py` a pure re-export facade (no definitions). (c) Consolidate small domain-root files into sub-packages: `domain/simulation/` (fill_pipeline, position_meta), `domain/reconciliation/` (report, engine), `domain/sessions/` (trading_session, session_status). |
| **From** | `domain/constants/__init__.py` (mixed facade + definitions), scattered small files at domain root |
| **To** | Clean sub-packages with pure-facade __init__.py files |
| **Touches** | `domain/constants/`, `domain/simulation/` (new), `domain/reconciliation/` (new), `domain/sessions/` (expanded), `domain/__init__.py` |
| **Test Strategy** | Import-linter contracts for new sub-package boundaries. mypy pass. |
| **Sequencing Note** | Depends on REF-6 (session renames), REF-10 (orchestration moved out of domain). |

---

### REF-14: Add Analytics Duplication Guardrail

| Field | Value |
|-------|-------|
| **Root Cause** | RC-6 (Absent/Inconsistent Coding Standards) |
| **Findings** | F39, F37 |
| **Action** | (a) Add import-linter contract preventing `analytics/paper` from importing `analytics/replay` internals and vice versa (both must go through `analytics/simulation/` shared layer). (b) Add ruff banned-api rules preventing analytics from importing concrete broker types. (c) Add a CI check for code duplication between analytics sub-packages (e.g., `vulture` or custom AST comparison). |
| **From** | No existing guardrail |
| **To** | Import-linter contract + ruff rules + CI duplication check |
| **Touches** | `pyproject.toml` (import-linter contracts, ruff config), `.pre-commit-config.yaml` (new hook) |
| **Test Strategy** | Import-linter test suite. CI pipeline verification. |
| **Sequencing Note** | Depends on REF-5 (simulation consolidation) being complete; the contract enforces the new structure. |

---

### REF-15: Expand mypy Strict Coverage

| Field | Value |
|-------|-------|
| **Root Cause** | RC-6 (Absent/Inconsistent Coding Standards) |
| **Findings** | F36, F38 |
| **Action** | (a) Create a mypy strict-mode allowlist that grows each sprint. (b) For each module cleaned of `dict[str, Any]` (REF-11) and string literals (REF-2), enable mypy strict. (c) Enforce file LOC limit (ADR-011) on all files, including grandfathered ones; add a `--force` flag for documented exceptions. |
| **From** | mypy ERROR-mode on clean modules only |
| **To** | mypy strict on all modules (gradual rollout) |
| **Touches** | `pyproject.toml` (mypy config), `.pre-commit-config.yaml` (mypy hook expansion) |
| **Test Strategy** | CI mypy strict pass on allowlisted modules. Allowlist must never shrink (only grow). |
| **Sequencing Note** | Ongoing; starts after REF-2 and REF-11 begin delivering clean modules. |

---

### Dependency Graph

```
REF-1 (exceptions)  ──────────────────────────────────────┐
REF-2 (PositionSide) ────────────────────────────────────┐│
REF-3 (hardcoded NSE) ──────────────────────────────────┐││
REF-4 (OrderIntent) ───────────────────────────────────┐│││
REF-6 (session renames) ──────────────────────────────┐││││
REF-7 (TimeService) ─────────────────────────────────││││││
REF-8 (Config consolidation) ────────────────────────│││││││
                                                      │││││││
REF-5 (simulation consolidation) ← REF-2, REF-4      │││││││
                                                      │││││││
REF-9 (canonical imports) ← REF-1, REF-2, REF-4, REF-6│││││
                                                      │││││
REF-10 (orchestration out of domain) ← REF-5         │││││
                                                      ││││
REF-11 (typed models) ← REF-5                        ││││
                                                      │││
REF-12 (getattr removal) ─── independent             │││
                                                      ││
REF-13 (flatten constants) ← REF-6, REF-10          ││
                                                      │
REF-14 (duplication guardrail) ← REF-5               │
                                                      │
REF-15 (mypy expansion) ← REF-2, REF-11 ────────────┘
```

**Parallelizable waves:**
- **Wave 1** (no dependencies): REF-1, REF-2, REF-3, REF-4, REF-6, REF-7, REF-8, REF-12
- **Wave 2** (after Wave 1): REF-5, REF-9
- **Wave 3** (after Wave 2): REF-10, REF-11, REF-13, REF-14
- **Ongoing**: REF-15

---

## PHASE 5 - Structural Recommendations

### 5.1 Proposed Directory Structure

```
src/
├── domain/
│   ├── __init__.py                    # Minimal: version only, no re-exports
│   ├── entities/
│   │   ├── order.py                   # Order, OrderRequest, ModifyOrderRequest
│   │   ├── position.py                # Position, PositionState
│   │   ├── trade.py                   # Trade
│   │   └── instrument.py              # Instrument aggregate root (NEW, see F20)
│   ├── enums.py                       # Side, OrderStatus, ProductType, OrderType, Validity, BrokerId, PositionSide
│   ├── market_enums.py                # Exchange, ExchangeSegment, InstrumentType, OptionType
│   ├── exceptions.py                  # Unified exception hierarchy (REF-1)
│   ├── value_objects.py               # Money, Quantity (enforce usage)
│   ├── ports/
│   │   ├── protocols.py               # DataProvider, ExecutionProvider
│   │   ├── broker_gateway.py          # OrderTransportPort, BrokerStreamHandle
│   │   └── event_publisher.py         # EventBusPort, EventPublisher
│   ├── events/
│   │   └── types.py                   # DomainEvent base
│   ├── constants/
│   │   ├── __init__.py                # Pure re-export facade only
│   │   ├── auth.py
│   │   ├── defaults.py
│   │   ├── exchanges.py
│   │   ├── market.py
│   │   ├── observability.py
│   │   ├── oms.py                     # NEW: moved from __init__.py
│   │   ├── reconciliation.py          # NEW: moved from __init__.py
│   │   ├── resilience.py
│   │   ├── risk.py
│   │   ├── segments.py
│   │   └── timeouts.py
│   ├── sessions/
│   │   ├── trading_session.py         # TradingSession, SessionStatus (canonical)
│   │   └── connectivity.py            # ConnectivityStatus (renamed from session_status.py, REF-6)
│   ├── market/
│   │   └── exchange.py                # Exchange entity, MarketHours (renamed from TradingSession, REF-6)
│   ├── execution_contracts.py         # OrderIntent (durable), SubmissionOutcome, LedgerFillRecord
│   ├── orders/
│   │   ├── intent.py                  # OrderCommand (renamed from OrderIntent, REF-4)
│   │   └── requests.py               # OrderRequest, SliceOrderRequest, OrderPreview
│   ├── status_mapper.py              # StatusMapperRegistry
│   └── extensions/                    # Extension capability protocols (typed payloads, REF-11)
│
├── application/
│   ├── __init__.py
│   ├── services/
│   │   ├── trading_costs_service.py   # NEW: fee calculations (REF-10)
│   │   ├── simulation_orchestrator.py # NEW: fill pipeline + projection (REF-10)
│   │   ├── reconciliation_service.py  # NEW: reconciliation engine (REF-10)
│   │   ├── instrument_registry.py
│   │   └── download_engine.py
│   ├── oms/
│   │   └── ...                        # Order management
│   ├── composer/
│   │   └── factory.py
│   └── ports.py                       # Mutable resolver (consider deprecation in favor of composition root)
│
├── infrastructure/
│   ├── __init__.py
│   ├── time_service.py                # Single TimeService (REF-7)
│   ├── event_bus/
│   ├── resilience/
│   │   ├── circuit_breaker.py
│   │   ├── retry_executor.py
│   │   └── rate_limiter.py
│   └── security/
│
├── brokers/
│   ├── common/
│   │   ├── order_validation.py        # Shared lot-size, tick-alignment validation
│   │   └── api/
│   ├── dhan/
│   │   ├── domain.py                  # Explicit imports only (REF-12)
│   │   ├── status_mapper.py           # No import-time side effects (REF-27)
│   │   └── ...
│   └── upstox/
│
├── analytics/
│   ├── __init__.py
│   ├── simulation/                    # NEW: shared simulation layer (REF-5)
│   │   ├── __init__.py
│   │   ├── models.py                  # SimTrade, SimPosition, SimSession
│   │   ├── signal_processor.py        # Single SignalProcessor
│   │   └── position_closer.py         # Single PositionCloser
│   ├── paper/
│   │   ├── adapter.py                 # Thin adapter configuring simulation/ shared classes
│   │   └── models.py                  # PaperConfig only (trade/position types in simulation/)
│   ├── replay/
│   │   ├── adapter.py                 # Thin adapter configuring simulation/ shared classes
│   │   └── models.py                  # ReplayConfig, ReplayItem only
│   ├── backtest/
│   ├── strategy/
│   ├── scanner/
│   ├── views/
│   ├── walk_forward/
│   ├── intraday/
│   ├── core/
│   └── shared/                        # Eliminated after REF-5 (trade_types absorbed into simulation/)
│
├── interface/
│   ├── api/
│   │   ├── config.py                  # DELETED: merged into config/schema.py (REF-8)
│   │   └── ...
│   └── cli/
│
├── config/
│   ├── schema.py                      # AppConfig: single configuration root (REF-8)
│   └── ...
│
├── runtime/
│   ├── composition.py                 # Composition root: only layer that wires concrete brokers
│   └── ...                            # No TimeService (moved to infrastructure, REF-7)
│
├── datalake/
│   └── ...
│
└── tradex/
    └── ...
```

### 5.2 Boundary Rules

These rules are enforceable via import-linter contracts and ruff banned-api rules:

| Rule ID | Rule | Enforced By | Root Cause Addressed |
|---------|------|-------------|----------------------|
| **B-1** | `domain/` must not import from `application/`, `infrastructure/`, `brokers/`, `analytics/`, `interface/` | import-linter (existing) | RC-4 |
| **B-2** | `infrastructure/` must not import from `brokers/`, `analytics/`, `interface/` | import-linter (existing) | RC-4 |
| **B-3** | `analytics/paper/` must not import from `analytics/replay/` and vice versa; both import from `analytics/simulation/` | import-linter (NEW, REF-14) | RC-1, RC-6 |
| **B-4** | `application/` must not import concrete broker modules; uses domain ports only | import-linter (existing) | RC-4 |
| **B-5** | `interface/` must not import from `brokers/` directly | import-linter (existing) | RC-4 |
| **B-6** | `runtime/` is the ONLY layer permitted to import concrete broker modules | import-linter (existing) | RC-4 |
| **B-7** | No module may use `__getattr__` for re-exports | ruff custom rule (REF-12) | RC-4 |
| **B-8** | All domain types imported from owning submodule, never from `domain` or `domain.types` facade | ruff banned-api (REF-9) | RC-6 |
| **B-9** | String literals `"NSE"`, `"BUY"`, `"SELL"` banned in function signatures and logic paths; use domain enums | ruff banned-api (REF-2, REF-3) | RC-4, RC-6 |
| **B-10** | `dict[str, Any]` banned in new code; typed models required | mypy strict + ruff custom rule (REF-11) | RC-3 |

### 5.3 Checkable Coding Standards

These 8 standards extend the existing `context/code-standards.md` and are machine-checkable:

| # | Standard | Check Mechanism | Finding Addressed |
|---|----------|----------------|-------------------|
| **CS-1** | **Canonical import paths**: All domain types imported from owning submodule (`from domain.enums import Side`), never from facade (`from domain import Side`). No type aliases (`OrderSide`, `DomainSide`). | ruff banned-api rule + import-linter | F34, F35 |
| **CS-2** | **No stringly-typed domain concepts**: Exchange, Side, PositionSide, OrderStatus always use domain enums. String literals `"NSE"`, `"BUY"`, `"SELL"`, `"LONG"`, `"SHORT"` banned in logic paths. | ruff banned-api rule | F24, F25 |
| **CS-3** | **Single exception hierarchy**: All exceptions imported from `domain.exceptions`. No parallel hierarchies. Infrastructure does not re-export domain exceptions. | import-linter + grep test | F21, F23 |
| **CS-4** | **No import-time side effects**: Importing a module must not register handlers, mutate global state, or configure services. Registration happens in `runtime/composition.py` only. | Custom AST checker in pre-commit | F27 |
| **CS-5** | **Typed models over dict[str, Any]**: All data shapes with known structure use dataclasses or Pydantic models. `dict[str, Any]` permitted only for truly dynamic/external data (e.g., JSON from third-party APIs at the boundary). | mypy strict + ruff custom rule | F19 |
| **CS-6** | **Single definition rule**: Each type, enum, and dataclass defined in exactly one location. No parallel definitions across layers. Deduplication verified by name-similarity CI check. | Custom CI check (name similarity > 0.8 across modules) | F1, F2, F3, F4, F5, F6 |
| **CS-7** | **File size limit (ADR-011)**: All files must be under the LOC limit. No grandfathering; documented exceptions require ADR approval. | check-file-loc pre-commit hook (enforced on ALL files) | F38 |
| **CS-8** | **Composition root exclusivity**: Only `runtime/` may instantiate concrete broker classes. All other layers use ports (Protocols) and receive implementations via dependency injection. | import-linter (existing) + mypy Protocol verification | F16 |

### 5.4 Guardrails to Prevent Recurrence

| Guardrail | Implementation | Prevents |
|-----------|---------------|----------|
| **G-1: Import-linter contract suite** | Expand existing 13 contracts to ~18 (add B-3, B-7, B-8, B-9, B-10). Run in CI on every PR. | New boundary violations, new facade imports, new stringly-typed code |
| **G-2: Ruff banned-api expansion** | Add banned patterns for: `"NSE"` string default, `"BUY"`/`"SELL"` literals, `__getattr__` re-exports, `dict[str, Any]` in new code, facade imports. | RC-4 and RC-6 violations at commit time |
| **G-3: mypy strict allowlist** | Maintain a allowlist file (`mypy-strict-allowlist.txt`) that only grows. CI runs mypy strict on allowlisted modules. New modules must start in strict mode. | Gradual elimination of type errors; prevents regression |
| **G-4: Duplication detection CI job** | Nightly CI job running AST-based code similarity detection between analytics sub-packages. Fails PR if similarity > 80% between any two modules > 100 lines. | RC-1 parallel model duplication |
| **G-5: Pre-commit architecture fitness function** | Custom pytest test (`tests/architecture/`) that: (a) verifies no `__getattr__` re-exports, (b) verifies no string defaults for exchange/side, (c) verifies exception hierarchy is unified, (d) verifies no `dict[str, Any]` in new code. Run in pre-commit + CI. | All root causes, automated |
| **G-6: ADR-required structural changes** | Any new top-level module, new Config class, or new re-export facade requires an ADR documenting the decision, alternatives considered, and enforcement mechanism. | RC-5 premature splitting, RC-2 missing service layer |
| **G-7: Name collision registry** | Maintain a registry (machine-checked) of all type names across the codebase. CI fails if a new type name has > 0.8 similarity to an existing type name in a different module. | RC-1 duplicate type definitions |
| **G-8: Zero-parity verification** | Existing golden dataset tests expanded to run on every PR touching analytics/simulation/, analytics/paper/, or analytics/replay/. Verifies that paper and replay produce identical outputs for identical inputs. | RC-1 simulation model divergence |

---

### Summary of Traceability

| Root Cause | Findings | Refactoring Tasks | Guardrails |
|------------|----------|-------------------|------------|
| RC-1: Missing shared vocabulary | F1-F11 | REF-2, REF-4, REF-5, REF-6, REF-7 | G-4, G-6, G-7, G-8 |
| RC-2: Missing service/use-case layer | F12-F17 | REF-8, REF-10 | G-6 |
| RC-3: Missing domain model | F18-F22 | REF-11, REF-20 (instrument aggregate) | G-3, G-5 |
| RC-4: Boundary violations | F23-F29 | REF-3, REF-12 | G-1, G-2, G-5 |
| RC-5: Premature file splitting | F30-F33 | REF-13 | G-6 |
| RC-6: Absent/inconsistent standards | F34-F39 | REF-9, REF-14, REF-15 | G-1, G-2, G-3, G-5 |
