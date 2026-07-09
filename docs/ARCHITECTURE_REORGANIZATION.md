# TradeXV2 — Architectural Reorganization Plan

> **Author:** Principal Engineering Review
> **Principles:** Clean Architecture (Uncle Bob), SOLID, YAGNI, Agile Incrementalism
> **Date:** 2026-07-10
> **Branch:** `refactor/structural-cleanup`
> **Grounding:** Every recommendation below is traced to a specific file, import, or test.

---

## Part 1: The Root Cause

### The One Problem That Causes Everything Else

The codebase has **one architectural cancer**: `tradex/runtime/` is a **coupling hub** that mixes three Clean Architecture layers into one namespace:

| What lives in `tradex/runtime/` | Should live in | Why |
|---|---|---|
| `broker_port.py`, `capabilities.py`, `models.py`, `errors.py`, `policy.py`, `extensions/`, `options/` | **`domain/`** | Domain abstractions that define the business vocabulary |
| `router.py`, `registry.py`, `stream_orchestrator.py`, `historical_coordinator.py`, `quota_scheduler.py`, `provenance.py`, `services/`, `reconciliation/` | **`application/`** | Orchestration logic that wires domain use cases |
| `auth/`, `resilience/`, `observability/`, `connection/`, `connection_pool.py`, `settings.py`, `clock.py` | **`infrastructure/`** | Concrete implementations of external concerns |

**The proof is in the imports:**

```python
# application/composer/factory.py — application importing from what SHOULD be domain
from tradex.runtime.broker_port import CommonBrokerGateway      # ← domain type
from tradex.runtime.historical_coordinator import HistoricalQuery  # ← application type
from tradex.runtime.router import BrokerRouter                     # ← application type
from tradex.runtime.stream_orchestrator import StreamOrchestrator  # ← application type
from tradex.runtime.registry import BrokerRegistry                 # ← application type
```

This creates a **dependency web** instead of a **dependency DAG**:

```
CORRECT (Clean Architecture):       ACTUAL (TradeXV2):

domain                              domain
  ↑                                   ↑
application                          tradex.runtime ←── COUPLING HUB
  ↑                                   ↑    ↑    ↑
infrastructure                      brokers  api  cli
  ↑                                   ↑
brokers                             infrastructure
  ↑
interface (API/CLI)
```

### Why This Causes All 87 Findings

| Finding Category | Root Cause |
|---|---|
| **12 God Classes** | tradex.runtime bundles too many concerns → classes grow to accommodate everything |
| **18 Duplicates** | Two implementations exist because there's no single canonical layer |
| **14 SOLID Violations** | Layer confusion makes it impossible to apply OCP/ISP/DIP correctly |
| **8 Tight Coupling** | Everything imports tradex.runtime → circular deps, shotgun surgery |
| **7 Over-Engineering** | Abstractions multiply because the layer boundaries are unclear |

---

## Part 2: The Architectural Fix

### The Dependency Rule (Bob Martin, Clean Architecture Ch. 5)

> *"Source code dependencies must point only inward, toward higher-level policies."*

This means:
1. **Domain** imports NOTHING from outer layers
2. **Application** imports ONLY from domain
3. **Infrastructure** imports ONLY from domain (to implement ports)
4. **Brokers** import ONLY from domain (to implement broker ports)
5. **Interface** (API/CLI) imports ONLY from application

### Target Architecture (5 Layers, DAG Not Web)

```
┌─────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER                       │
│  api/          (REST + WebSocket)                       │
│  cli/          (CLI + TUI)                              │
│                                                          │
│  Depends on: application/                                │
├─────────────────────────────────────────────────────────┤
│                    ADAPTER LAYER                         │
│  brokers/       (Dhan, Upstox, Paper)                   │
│  api/routers/   (route handlers)                        │
│                                                          │
│  Depends on: domain/ (ports + entities)                 │
├─────────────────────────────────────────────────────────┤
│                APPLICATION LAYER                         │
│  application/    (OMS, Execution, Trading, Composer)     │
│  runtime/        (bootstrap, DI, production config)      │
│                                                          │
│  Depends on: domain/ ONLY                                │
├─────────────────────────────────────────────────────────┤
│                INFRASTRUCTURE LAYER                      │
│  infrastructure/ (event bus, cache, DB, observability)   │
│  analytics/      (feature computation, views)            │
│  datalake/       (storage, ingestion, quality)           │
│                                                          │
│  Depends on: domain/ (implements ports)                  │
├─────────────────────────────────────────────────────────┤
│                    DOMAIN LAYER                          │
│  domain/          (entities, VOs, ports, events, enums)  │
│                                                          │
│  Depends on: NOTHING outward                             │
│  Already clean ✅                                        │
└─────────────────────────────────────────────────────────┘
```

### Dependency Graph (DAG)

```
domain/ ◄── application/ ◄── api/
                ↑              cli/
                ↑
          infrastructure/ ◄── brokers/
                ↑
            analytics/
            datalake/
```

**Every arrow points INWARD. No cycles. No webs.**

---

## Part 3: The Module Map (Top Level → Leaf Level)

### Layer 1: Domain (the stable center)

**Location:** `domain/` (promoted from `src/domain/`)

Already clean. Contains 230 files across 30+ subdirectories. No changes to internal structure needed.

**What moves INTO domain from tradex.runtime:**

| Source | Target | Why |
|---|---|---|
| `tradex/runtime/broker_port.py` (178L) | `domain/ports/broker_gateway.py` | Domain abstraction |
| `tradex/runtime/capabilities.py` (19L) | `domain/value_objects/capability.py` | Domain value object |
| `tradex/runtime/models.py` (180L) | `domain/models/routing.py` | Domain models |
| `tradex/runtime/dtos.py` (62L) | `domain/models/dtos.py` | Domain DTOs |
| `tradex/runtime/errors.py` (77L) | `domain/errors.py` (extend existing) | Error hierarchy belongs in domain |
| `tradex/runtime/gateway_errors.py` (14L) | `domain/errors.py` | Error types |
| `tradex/runtime/policy.py` (216L) | `domain/policies/source_selection.py` | Domain policy |
| `tradex/runtime/extensions/` (375L) | `domain/extensions/` | Domain extension contracts |
| `tradex/runtime/options/` (252L) | `domain/options/` (merge with existing) | Domain option chain logic |

**Total domain files after move:** ~230 + ~35 new = ~265 files

### Layer 2: Application (orchestration)

**Location:** `application/` (already exists, ~60 files)

**What moves INTO application from tradex.runtime:**

| Source | Target | Why |
|---|---|---|
| `tradex/runtime/router.py` (257L) | `application/composer/router.py` | Orchestration |
| `tradex/runtime/registry.py` (196L) | `application/composer/registry.py` | Orchestration |
| `tradex/runtime/stream_orchestrator.py` (1040L) | `application/streaming/orchestrator.py` | Orchestration |
| `tradex/runtime/historical_coordinator.py` (703L) | `application/data/historical_coordinator.py` | Orchestration |
| `tradex/runtime/quota_scheduler.py` (452L) | `application/scheduling/quota_scheduler.py` | Orchestration |
| `tradex/runtime/provenance.py` (143L) | `application/data/provenance.py` | Orchestration |
| `tradex/runtime/submission_pipeline.py` (205L) | `application/execution/submission_pipeline.py` | Orchestration |
| `tradex/runtime/candle_aggregator.py` (232L) | `application/streaming/candle_aggregator.py` | Orchestration |
| `tradex/runtime/factory.py` (55L) | `application/composer/factory.py` (merge) | Orchestration |
| `tradex/runtime/reconciliation/` (210L) | `application/oms/reconciliation/` | Application service |
| `tradex/runtime/services/` (1873L) | `application/services/` | Application services |

**New application subdirectories:**
```
application/
├── oms/               (existing — order management)
├── execution/         (existing — order execution)
├── composer/          (existing + router, registry from runtime)
├── trading/           (existing — trading orchestrator)
├── streaming/         (NEW — stream_orchestrator, candle_aggregator)
├── data/              (NEW — historical_coordinator, provenance)
├── scheduling/        (NEW — quota_scheduler)
├── services/          (NEW — data_validator, instrument_registry, etc.)
└── reconciliation/    (NEW — reconciliation engine from runtime)
```

**Total application files after move:** ~60 + ~50 new = ~110 files

### Layer 3: Infrastructure (implementations)

**Location:** `infrastructure/` (absorb from current infrastructure/ + tradex.runtime/)

**What moves INTO infrastructure from tradex.runtime:**

| Source | Target | Why |
|---|---|---|
| `tradex/runtime/auth/` (1457L) | `infrastructure/auth/` | Infrastructure |
| `tradex/runtime/resilience/` (1298L) | `infrastructure/resilience/` | Infrastructure |
| `tradex/runtime/observability/` (1131L) | `infrastructure/observability/` | Infrastructure |
| `tradex/runtime/connection/` (370L) | `infrastructure/connection/` | Infrastructure |
| `tradex/runtime/connection_pool.py` (334L) | `infrastructure/pool/` | Infrastructure |
| `tradex/runtime/ssl_hardening.py` (157L) | `infrastructure/security/` | Infrastructure |
| `tradex/runtime/settings.py` (147L) | `infrastructure/config/` | Infrastructure |
| `tradex/runtime/clock.py` (23L) | `infrastructure/time/` | Infrastructure |
| `tradex/runtime/build_info.py` (65L) | `infrastructure/` | Infrastructure |
| `tradex/runtime/async_compat.py` (9L) | `infrastructure/async/` | Infrastructure |
| `tradex/runtime/infrastructure.py` (138L) | `infrastructure/broker_infrastructure.py` | Infrastructure |
| `tradex/runtime/adapters/` (419L) | `infrastructure/adapters/` | Adapter implementations |
| `tradex/runtime/mappers/` (113L) | `infrastructure/mappers/` | Adapter mappers |
| `tradex/runtime/gateway.py` (19L) | `infrastructure/gateway/` | Gateway impl |
| `tradex/runtime/gateway_execution.py` (103L) | `infrastructure/gateway/` | Gateway impl |
| `tradex/runtime/gateway_factory.py` (374L) | `infrastructure/gateway/factory.py` | Gateway impl |
| `tradex/runtime/session_infra.py` (88L) | `infrastructure/session/` | Session impl |
| `tradex/runtime/env_loader.py` (10L) | `infrastructure/config/` | Config loading |

**Total infrastructure files after move:** ~82 + ~80 new = ~162 files

### Layer 4: Brokers (adapter implementations)

**Location:** `brokers/` (restructure dhan from flat to organized)

Internal structure is fine — brokers implement domain ports. The key change is that brokers import from `domain/` (for ports/types) instead of `tradex.runtime/`.

### Layer 5: Interface (API + CLI)

**Location:** `api/` + `cli/` (already exist, well-structured)

The key change is that API/CLI import from `application/` instead of `tradex/runtime/`.

---

## Part 4: The tradex/ Package (Public SDK)

After the reorganization, `tradex/` becomes **only** the public SDK facade:

```python
# tradex/session.py — the only file users import
from domain.universe import Universe
from application.composer.factory import create_composers

class BrokerSession:
    """Public SDK entry point. Users never see internal layers."""
    
    @classmethod
    def connect(cls, broker: str = "paper") -> "BrokerSession":
        composers = create_composers(broker)
        return cls(composers)
```

**tradex/ re-exports (backward compat facade):**
```python
# tradex/__init__.py — re-exports for public API
from tradex.session import BrokerSession

# tradex/runtime/__init__.py — backward compat facade
# All imports from tradex.runtime.X now resolve to the correct layer:
from domain.ports.broker_gateway import CommonBrokerGateway  # was broker_port
from application.composer.router import BrokerRouter          # was router
from infrastructure.resilience.errors import TradeXV2Error    # was errors
# etc.
```

This means **zero breaking changes** for existing importers during migration. The facade allows gradual migration.

---

## Part 5: The Migration Strategy

### Principle: Incremental, Test-Gated, Reversible

Uncle Bob says: *"Don't refactor and add features at the same time."*

We refactor in a specific order that maintains a green test suite at every commit.

### Wave 1: Establish the Facade (no moves, just shims)

**Goal:** Create `tradex/runtime/` as a thin re-export layer. No code moves yet.

```python
# tradex/runtime/broker_port.py — becomes:
"""Backward-compat facade. Canonical location: domain/ports/broker_gateway.py"""
from domain.ports.broker_gateway import *  # noqa

# tradex/runtime/router.py — becomes:
"""Backward-compat facade. Canonical location: application/composer/router.py"""
from application.composer.router import *  # noqa
```

**This is the key insight:** By making tradex.runtime a facade FIRST, we can move code in later phases without breaking any imports.

**Agent assignment:**
- Agent-γ: Create facades for all 112 tradex/runtime files
- Agent-ζ: Run tests after each batch

**Validation gate:**
```bash
PYTHONPATH="src:." pytest tests/ -x -q  # ALL tests must pass
```

**Duration:** 1 day
**Risk:** LOW (just re-exports, no logic changes)

### Wave 2: Move Domain Abstractions

**Goal:** Move pure domain types from tradex.runtime into domain/.

```
tradex/runtime/broker_port.py    → domain/ports/broker_gateway.py
tradex/runtime/capabilities.py   → domain/value_objects/capability.py
tradex/runtime/models.py         → domain/models/routing.py
tradex/runtime/dtos.py           → domain/models/dtos.py
tradex/runtime/errors.py         → domain/errors.py (extend)
tradex/runtime/policy.py         → domain/policies/source_selection.py
tradex/runtime/extensions/       → domain/extensions/ (merge)
tradex/runtime/options/          → domain/options/ (merge)
```

**After move:** The `tradex/runtime/` files become shims pointing to `domain/`.

**Agent assignment:**
- Agent-β: Move domain types, update all importers
- Agent-ζ: Run architecture tests + import linter

**Validation gate:**
```bash
PYTHONPATH="src:." pytest tests/architecture/test_domain_isolation.py -x -v
PYTHONPATH="src:." lint-imports --config pyproject.toml
```

**Duration:** 1 day
**Risk:** MEDIUM (import path changes)

### Wave 3: Move Application Orchestration

**Goal:** Move orchestration logic from tradex.runtime into application/.

```
tradex/runtime/router.py                 → application/composer/router.py
tradex/runtime/registry.py               → application/composer/registry.py
tradex/runtime/stream_orchestrator.py    → application/streaming/orchestrator.py
tradex/runtime/historical_coordinator.py → application/data/historical_coordinator.py
tradex/runtime/quota_scheduler.py        → application/scheduling/quota_scheduler.py
tradex/runtime/provenance.py             → application/data/provenance.py
tradex/runtime/submission_pipeline.py    → application/execution/submission_pipeline.py
tradex/runtime/candle_aggregator.py      → application/streaming/candle_aggregator.py
tradex/runtime/factory.py                → application/composer/factory.py (merge)
tradex/runtime/reconciliation/           → application/oms/reconciliation/
tradex/runtime/services/                 → application/services/
```

**Agent assignment:**
- Agent-δ: Move orchestration, update all importers
- Agent-ε: Fix broken tests
- Agent-ζ: Run full test suite

**Validation gate:**
```bash
PYTHONPATH="src:." pytest tests/architecture/ -x -q
PYTHONPATH="src:." pytest application/oms/tests/ -x -q
PYTHONPATH="src:." pytest tests/api/ -x -q
PYTHONPATH="src:." pytest cli/tests/ -x -q
```

**Duration:** 2 days
**Risk:** HIGH (most importers live here)

### Wave 4: Move Infrastructure

**Goal:** Move infrastructure implementations from tradex.runtime into infrastructure/.

```
tradex/runtime/auth/           → infrastructure/auth/
tradex/runtime/resilience/     → infrastructure/resilience/
tradex/runtime/observability/  → infrastructure/observability/
tradex/runtime/connection/     → infrastructure/connection/
tradex/runtime/connection_pool → infrastructure/pool/
tradex/runtime/ssl_hardening   → infrastructure/security/
tradex/runtime/settings        → infrastructure/config/
tradex/runtime/clock           → infrastructure/time/
tradex/runtime/gateway_*       → infrastructure/gateway/
tradex/runtime/adapters/       → infrastructure/adapters/
tradex/runtime/mappers/        → infrastructure/mappers/
tradex/runtime/session_infra   → infrastructure/session/
tradex/runtime/infrastructure  → infrastructure/broker_infrastructure
tradex/runtime/build_info      → infrastructure/
tradex/runtime/async_compat    → infrastructure/async/
tradex/runtime/env_loader      → infrastructure/config/
```

**Agent assignment:**
- Agent-γ: Move infrastructure, merge with existing infrastructure/
- Agent-ζ: Validate

**Validation gate:**
```bash
PYTHONPATH="src:." pytest tests/ -x -q --timeout=120
PYTHONPATH="src:." lint-imports --config pyproject.toml
```

**Duration:** 1 day
**Risk:** MEDIUM (infrastructure is already partially there)

### Wave 5: Promote domain/ and Update Facade

**Goal:** Promote `src/domain/` to root level. Update tradex.runtime facade to point to new locations.

```
src/domain/ → domain/  (or keep src/domain/ with pythonpath)
tradex/runtime/*.py → all become thin re-exports to final locations
```

**Agent assignment:**
- Agent-α: Handle the directory promotion
- Agent-ζ: Final validation

**Duration:** 1 day
**Risk:** LOW (facade already handles this)

### Wave 6: God Class Decomposition

**Goal:** Break the 12 god classes into focused collaborators.

Now that the layers are clean, we can decompose classes without worrying about layer violations.

**Phase 4a-4e from the original plan apply here, but with cleaner imports.**

**Duration:** 3 days
**Risk:** HIGH (behavioral changes)

### Wave 7: Broker Restructuring + Cleanup

**Goal:** Restructure brokers/dhan/ flat files, clean scripts/, enforce naming.

**Phases 9, 10 from the original plan.**

**Duration:** 2 days
**Risk:** MEDIUM (file moves)

---

## Part 6: The Import Migration

### The tradex.runtime Facade (backward compat)

After all moves, `tradex/runtime/` becomes a thin facade:

```python
# tradex/runtime/__init__.py
"""Backward-compat facade. Import from canonical locations instead."""

# Domain types
from domain.ports.broker_gateway import CommonBrokerGateway
from domain.value_objects.capability import BrokerCapabilities
from domain.models.routing import OperationKind, RoutingRequest
from domain.errors import TradeXV2Error, BrokerError, OrderError

# Application orchestration
from application.composer.router import BrokerRouter
from application.composer.registry import BrokerRegistry
from application.streaming.orchestrator import StreamOrchestrator
from application.data.historical_coordinator import HistoricalDataCoordinator

# Infrastructure
from infrastructure.resilience.circuit_breaker import CircuitBreaker
from infrastructure.auth.token import TokenManager
from infrastructure.observability.audit import emit_routing_decision
```

**Deprecation timeline:**
1. Phase 1-5: Facade exists, all imports work
2. Phase 6: Add `DeprecationWarning` to facade imports
3. Phase 7+: Remove facade after all consumers migrate

### Importer Migration Order

```
Priority 1 (highest): application/ — 16 imports from tradex.runtime
Priority 2: brokers/common/ — 5 imports from tradex.runtime
Priority 3: api/ — 4 imports from tradex.runtime
Priority 4: cli/ — many imports via broker_service
Priority 5: tests/ — many imports (lower priority, can use facade)
Priority 6: scripts/ — utility scripts (lowest priority)
```

---

## Part 7: The New Dependency Contracts

### Updated `pyproject.toml` import-linter

```toml
[tool.importlinter]
root_packages = ["domain", "application", "infrastructure", "brokers", 
                 "analytics", "datalake", "api", "cli", "tradex"]

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

# Rule 5: API/CLI depend only on application
[[tool.importlinter.contracts]]
name = "Interface depends on application"
type = "forbidden"
source_modules = ["api", "cli"]
forbidden_modules = ["infrastructure", "brokers", "analytics", "datalake"]
```

### Updated architecture test

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

---

## Part 8: What We Gain

### Before (Current State)

```
12 God Classes, 18 Duplicates, 14 SOLID Violations,
8 Tight Couplings, 7 Over-Engineering, 2 Primitive Obsessions
= 87 findings, dependency WEB
```

### After (Target State)

| Metric | Before | After |
|---|---|---|
| Layers | 10+ overlapping | 5 clean layers |
| tradex/runtime files | 112 (coupling hub) | 0 (facade only) |
| Dependency direction violations | 8+ | 0 |
| God classes | 12 | 0 (all decomposed) |
| Duplicate modules | 18 | 0 (single source of truth) |
| Empty packages | 5 | 0 |
| Runtime state in source | 12 files | 0 |
| `__pycache__` dirs | 226 | 0 (gitignored) |
| Test coverage | ~400 tests | ~450+ tests |
| Import linter contracts | 8 (with workarounds) | 5 (clean) |

### The Key Metric: Dependency Direction

```
BEFORE: 8 violations, circular deps, shotgun surgery
AFTER:  0 violations, clean DAG, single responsibility per layer
```

---

## Part 9: Timeline & Agents

### 6-Week Execution Plan

```
Week 1: Wave 1 (Facade) + Wave 2 (Domain moves)
  Day 1: [γ] Create tradex.runtime facade for all 112 files
  Day 2: [γ] Verify facade — ALL tests pass with zero code changes
  Day 3: [β] Move domain abstractions (7 files + subdirs)
  Day 4: [β] Update importers for domain moves
  Day 5: [ζ] Architecture test gate — domain isolation verified

Week 2: Wave 3 (Application moves)
  Day 1-2: [δ] Move orchestration (11 files + services/)
  Day 3: [δ] Move reconciliation
  Day 4: [ε] Fix broken tests
  Day 5: [ζ] Full regression gate

Week 3: Wave 4 (Infrastructure moves)
  Day 1-2: [γ] Move infrastructure (18 files + subdirs)
  Day 3: [γ] Merge with existing infrastructure/
  Day 4: [ζ] Import linter gate
  Day 5: [ζ] Full regression gate

Week 4: Wave 5 (Facade cleanup) + Wave 6 (God classes start)
  Day 1: [α] Promote domain/, update facade
  Day 2-4: [δ] Decompose Instrument, StreamOrchestrator, BrokerService
  Day 5: [ζ] Regression gate

Week 5: Wave 6 (God classes finish) + Wave 7 (Restructuring)
  Day 1-2: [δ] Decompose broker god classes (4d)
  Day 3: [δ] Decompose analytics god classes (4e)
  Day 4: [γ] Restructure brokers/dhan/ (9a)
  Day 5: [α] Categorize scripts/ (9b), clean pycache (6)

Week 6: Final cleanup + Documentation
  Day 1: [δ] SOLID fixes (5c, 5h), naming (10)
  Day 2: [ζ] Update docs, pyproject.toml, governance
  Day 3: [ALL] Final full regression
  Day 4: [ALL] Push, PR, review
  Day 5: Buffer
```

### Agent Assignments

| Agent | Waves | Focus |
|---|---|---|
| **α** | 1, 5, 7 | Facade creation, domain promotion, dead code cleanup |
| **β** | 2, 5f | Domain type moves, broker adapter DRY |
| **γ** | 1, 4, 7, 9 | Infrastructure moves, dhan restructure, scripts |
| **δ** | 3, 6, 10 | Application moves, god class decomposition, naming |
| **ε** | 3, 6 | Test repair, broken test recovery |
| **ζ** | ALL | Architecture tests, import linter, regression gates |

---

## Part 10: Risk Mitigation

### The Facade Pattern (Key Safety Net)

The `tradex.runtime` facade is the **single most important safety mechanism**:

1. **Phase 1:** Create facade — zero code changes, all tests pass
2. **Phases 2-4:** Move code — facade re-exports from new locations
3. **Phase 5:** Add deprecation warnings to facade
4. **Phase 7+:** Remove facade after all consumers migrate

**If anything breaks:** Revert to facade, everything still works.

### Test Gates (Non-Negotiable)

| Gate | When | Tests |
|---|---|---|
| Domain isolation | After every wave | `test_domain_isolation.py` |
| Import linter | After every wave | `lint-imports` |
| Unit tests | After every wave | `pytest tests/unit/` |
| Architecture tests | After every wave | `pytest tests/architecture/` |
| Full regression | End of each week | `pytest tests/` |
| Broker tests | After broker changes | `pytest brokers/*/tests/` |

### Rollback Strategy

```bash
# Per-wave rollback
git log --oneline  # find the wave commit
git revert <commit>  # undo that wave

# Full rollback (nuclear option)
git checkout refactor/brokers-consolidation  # back to before cleanup
```

---

## Part 11: The Guiding Principle

> *"The center of your application is not the database. It is not one or more of the frameworks you may be using. The center of your application is the use cases of your application."*
> — Robert C. Martin, Clean Architecture

In TradeXV2, the use cases are:
1. **Connect to a broker** and authenticate
2. **Stream market data** (quotes, depth, options)
3. **Place/modify/cancel orders** with risk checks
4. **Track positions and P&L** in real-time
5. **Run analytics** (scanners, indicators, backtests)
6. **Persist data** for research and replay

Every module in the codebase should exist to serve one or more of these use cases. If a module doesn't clearly serve a use case, it's either:
- **Wrong layer** (domain logic in infrastructure)
- **Wrong scope** (too many responsibilities)
- **Dead code** (should be deleted)

The reorganization above ensures every file is in the right layer, serving the right use case, with dependencies pointing in the right direction.

---

## Appendix A: Full File Movement Map

### Files Moving FROM `tradex/runtime/` TO `domain/` (~35 files)

```
tradex/runtime/broker_port.py              → domain/ports/broker_gateway.py
tradex/runtime/capabilities.py             → domain/value_objects/capability.py
tradex/runtime/models.py                   → domain/models/routing.py
tradex/runtime/dtos.py                     → domain/models/dtos.py
tradex/runtime/errors.py                   → domain/errors.py
tradex/runtime/gateway_errors.py           → domain/errors.py
tradex/runtime/policy.py                   → domain/policies/source_selection.py
tradex/runtime/policy_defaults.py          → domain/policies/defaults.py
tradex/runtime/extensions/__init__.py      → domain/extensions/__init__.py
tradex/runtime/extensions/forever_order.py → domain/extensions/forever_order.py
tradex/runtime/extensions/fundamentals.py  → domain/extensions/fundamentals.py
tradex/runtime/extensions/native_slice.py  → domain/extensions/native_slice.py
tradex/runtime/extensions/news.py          → domain/extensions/news.py
tradex/runtime/extensions/super_order.py   → domain/extensions/super_order.py
tradex/runtime/options/chain_normalizer.py → domain/options/chain_normalizer.py
tradex/runtime/options/gateway_facade.py   → domain/options/gateway_facade.py
```

### Files Moving FROM `tradex/runtime/` TO `application/` (~25 files)

```
tradex/runtime/router.py                   → application/composer/router.py
tradex/runtime/registry.py                 → application/composer/registry.py
tradex/runtime/stream_orchestrator.py      → application/streaming/orchestrator.py
tradex/runtime/candle_aggregator.py        → application/streaming/candle_aggregator.py
tradex/runtime/historical_coordinator.py   → application/data/historical_coordinator.py
tradex/runtime/provenance.py               → application/data/provenance.py
tradex/runtime/quota_scheduler.py          → application/scheduling/quota_scheduler.py
tradex/runtime/quota_decorator.py          → application/scheduling/quota_decorator.py
tradex/runtime/submission_pipeline.py      → application/execution/submission_pipeline.py
tradex/runtime/factory.py                  → application/composer/factory.py
tradex/runtime/reconciliation/engine.py    → application/oms/reconciliation/engine.py
tradex/runtime/services/data_validator.py  → application/services/data_validator.py
tradex/runtime/services/download_engine.py → application/services/download_engine.py
tradex/runtime/services/historical_data.py → application/services/historical_data.py
tradex/runtime/services/instrument_registry.py → application/services/instrument_registry.py
tradex/runtime/services/production_readiness.py → application/services/production_readiness.py
```

### Files Moving FROM `tradex/runtime/` TO `infrastructure/` (~50 files)

```
tradex/runtime/auth/*                      → infrastructure/auth/*
tradex/runtime/resilience/*                → infrastructure/resilience/*
tradex/runtime/observability/*             → infrastructure/observability/*
tradex/runtime/connection/*                → infrastructure/connection/*
tradex/runtime/connection_pool.py          → infrastructure/pool/connection_pool.py
tradex/runtime/ssl_hardening.py            → infrastructure/security/ssl_hardening.py
tradex/runtime/settings.py                 → infrastructure/config/settings.py
tradex/runtime/env_loader.py               → infrastructure/config/env_loader.py
tradex/runtime/clock.py                    → infrastructure/time/clock.py
tradex/runtime/build_info.py               → infrastructure/build_info.py
tradex/runtime/async_compat.py             → infrastructure/async/compat.py
tradex/runtime/infrastructure.py           → infrastructure/broker_infrastructure.py
tradex/runtime/gateway.py                  → infrastructure/gateway/base.py
tradex/runtime/gateway_execution.py        → infrastructure/gateway/execution.py
tradex/runtime/gateway_factory.py          → infrastructure/gateway/factory.py
tradex/runtime/session_infra.py            → infrastructure/session/infra.py
tradex/runtime/adapters/*                  → infrastructure/adapters/*
tradex/runtime/mappers/*                   → infrastructure/mappers/*
```

### Files Staying in `tradex/` (public SDK only)

```
tradex/__init__.py          → public re-exports
tradex/session.py           → BrokerSession (public API)
tradex/runtime/__init__.py  → backward-compat facade (thin re-exports)
```

---

## Appendix B: Before/After Dependency Graph

### BEFORE (Dependency Web)

```
                domain
                  ↑
            tradex.runtime ←──── coupling hub (112 files)
           ↗    ↑    ↑    ↖
    application brokers api cli
        ↑         ↑
    infrastructure  config
```

### AFTER (Clean DAG)

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

**Every arrow points inward. No cycles. No webs. No coupling hubs.**
