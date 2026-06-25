# ARCHITECTURE_V3.md — Repository Organisation & Structure Audit

**System**: TradeXV2 — Python-based, broker-agnostic algorithmic trading framework for Indian exchanges  
**Audit Date**: 2026-06-25  
**Auditor**: Principal Software Architect (Uncle Bob + Dr. Venkat methodology)  
**Scope**: Repository organisation, module boundaries, dependency direction, shared libraries, duplicate functionality, ownership, configuration, and proposed clean structure  
**Predecessor**: ARCHITECTURE_V2.md (SOLID violations and dependency analysis)

---

## Executive Summary

**Architectural Styles Detected**: Layered Architecture (domain/application/infrastructure) + Broker Adapter Pattern + Partial Hexagonal (ports/adapters declared but inconsistently applied)  
**Consistency Assessment**: ⚠️ Mixed — core layers exist but root-level orphans and cross-cutting imports undermine the discipline  
**Overall Architecture Health**: 🟠 High Risk — domain layer is clean but repository organisation obscures intent, duplicates critical functionality, and exposes real credentials  
**Total Findings**: 🔴 5 Critical | 🟠 8 High | �� 6 Medium | 🟢 3 Low | 💡 4 Recommendations

> *"The top-level folder structure should tell me what the system DOES — not what framework it uses. If your top-level folders are 'controllers', 'services', 'models', I know nothing about your business. If they are 'orders', 'payments', 'inventory', I know everything."* — Robert C. Martin

> *"A repository is a conversation with the next developer. Every folder name, every file name, every module boundary is a sentence in that conversation. Make sure it says what you mean."* — Dr. Venkat Subramaniam

---

## 1. Current Structure Analysis

Annotated with ✅ Good | ⚠️ Concern | 🔴 Violation

```
Trade_XV2/
├── .env.local                          🔴 REAL CREDENTIALS EXPOSED (tokens, API keys, PINs, TOTP secrets)
├── .env.example                        ✅ Good — template exists
├── .env.upstox                         ⚠️ Concern — secondary env file, inconsistent with .env.local
├── api_server.py                       🔴 Orphan root-level launcher (47 lines) — belongs in entry_points/
├── endpoints.py                        🔴 Orphan root-level broker endpoint registry (452 lines) — belongs in brokers/common/
├── indices.py                          🔴 Orphan root-level index symbol mapping (408 lines) — belongs in domain/ or brokers/common/
├── secrets_manager.py                  🔴 Orphan root-level secrets access (55 lines) — belongs in infrastructure/secrets/
├── conftest.py                         ⚠️ Root test fixtures (166 lines) — acceptable if truly cross-cutting
├── tradex                              ⚠️ Shell script entry point — unclear purpose
├── test_all_cli.sh                     🟢 Shell test script — acceptable
│
├── analytics/                          ✅ Good — business capability (quantitative analysis)
├── api/                                ✅ Good — business capability (external API surface)
├── application/                        ✅ Good — use case layer (but __all__ is empty)
├── brokers/                            ✅ Good — broker adapter layer
│   ├── common/                         ⚠️ Concern — 162 .py files, 55 dirs — approaching God module territory
│   ├── dhan/                           ✅ Good — broker-specific adapter
│   ├── upstox/                         ✅ Good — broker-specific adapter (but many empty __init__.py)
│   └── paper/                          ✅ Good — mock adapter for testing
├── cli/                                ✅ Good — business capability (command-line interface)
├── config/                             ⚠️ Concern — schema exists but configuration scattered elsewhere
├── datalake/                           ✅ Good — business capability (data persistence/retrieval)
├── domain/                             ✅ Good — domain layer (clean: 0 external imports, good __all__)
│   └── constants/                      ⚠️ Concern — configuration defaults leaking into domain
├── infrastructure/                     ✅ Good — infrastructure layer (22 .py files, clean dependency direction)
├── market_data/                        ⚠️ Concern — overlaps with brokers/* and datalake/* responsibilities
├── runtime/                            ⚠️ Concern — mixed concerns (bootstrap, config, SQLite dead-letter, runtime state JSON)
├── scripts/                            ⚠️ Concern — 27 scripts with unclear ownership and categorisation
├── tests/                              ⚠️ Concern — tests scattered (some co-located in modules, some here)
├── frontend/                           ✅ Good — separate UI concern
├── docs/                               ✅ Good — documentation
├── data/                               ⚠️ Concern — unclear purpose vs datalake/
├── archive/                            🟢 Archive — acceptable
├── htmlcov/                            🟢 Coverage output — acceptable (should be .gitignored)
├── .venv/                              🟢 Virtual environment — acceptable (should be .gitignored)
└── venv/                               🟢 Duplicate virtual environment — confusing
```

### Key Observations

1. **Top-level organisation screams "technical layers" not "business capabilities"**: `domain/`, `application/`, `infrastructure/` are architectural patterns, not business domains. A new developer cannot tell this is a quantitative trading platform from the folder names alone.

2. **5 orphan root-level .py files** (1,128 total lines) pollute the repository root and create implicit global modules that every other module imports from directly, bypassing all architectural boundaries.

3. **Dual virtual environments** (`.venv/` and `venv/`) suggest confusion about dependency management.

4. **Runtime state files** (`dhan-token-state.json`, `dhan-totp-cooldown.json`, `dead_letter.sqlite`) checked into repository root indicate missing separation of runtime artefacts from source code.

---

## 2. Module Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINTS                                   │
│    api_server.py ───┐   cli/ ───┐   scripts/ ───┐   tradex ───┐            │
│    (root orphan)    │           │   (uncategorized)│           │            │
└─────────┬──────────┘           └──────┬──────────┘           └────┬────────┘
          │                             │                          │
          ▼                             ▼                          ▼
┌──────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   api/           │    │   cli/               │    │   runtime/           │
│   (HTTP API)     │    │   (CLI commands)     │    │   (bootstrap/config) │
└────────┬─────────┘    └──────────┬───────────┘    └──────────┬───────────┘
         │                         │                           │
         ▼                         ▼                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        application/ (use cases)                          │
│   composer/  execution/  oms/  trading/                                  │
│   ✅ Clean: 0 broker-specific imports                                    │
└────────┬─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         domain/ (entities, rules)                        │
│   capabilities/ entities/ enums/ constants/ reconciliation/ requests/    │
│   ✅ Clean: 0 external imports — PERFECT                                 │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                      BROKER ADAPTERS (infrastructure)                    │
│                                                                          │
│  brokers/common/ ◄──── brokers/dhan/     brokers/upstox/   brokers/paper/│
│  (162 .py files)       🔴 imports         🔴 imports                      │
│   gateway.py           endpoints.py       endpoints.py                    │
│   settings.py          indices.py         indices.py                      │
│   oms/_internal/       secrets_manager.py secrets_manager.py              │
│                        🔴 cyclic deps     🔴 cyclic deps                  │
│                                                                          │
│  🔴 CRITICAL: broker adapters import ROOT-LEVEL files, bypassing         │
│     brokers/common/ and creating implicit global dependencies            │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                    SHARED / CROSS-CUTTING                                │
│                                                                          │
│  datalake/    analytics/    infrastructure/    market_data/    config/   │
│  (data layer) (quant)      (external svcs)    (market feeds)  (config)   │
│                                                                          │
│  ⚠️ market_data/ overlaps with brokers/*/market_data/                    │
│  ⚠️ datalake/ overlaps with data/                                       │
└──────────────────────────────────────────────────────────────────────────┘

DEPENDENCY DIRECTION SUMMARY:
  domain ← application ← api/cli/runtime ← infrastructure ← brokers ✅
  BUT: brokers/dhan/ → endpoints.py (root) 🔴 CYCLE VIA ROOT
  BUT: brokers/upstox/ → endpoints.py (root) 🔴 CYCLE VIA ROOT
  BUT: brokers/dhan/ → indices.py (root) 🔴 CYCLE VIA ROOT
  BUT: brokers/upstox/ → indices.py (root) 🔴 CYCLE VIA ROOT
  BUT: brokers/dhan/ → secrets_manager.py (root) 🔴 CYCLE VIA ROOT
  BUT: brokers/upstox/ → secrets_manager.py (root) 🔴 CYCLE VIA ROOT

🔴 ROOT-LEVEL FILES CREATE IMPLICIT GOD MODULE THAT EVERYONE IMPORTS
```

---

## 3. Duplicate Functionality Map

| Concept | Location 1 | Location 2 | Canonical Location | Severity |
|---------|-----------|-----------|-------------------|----------|
| **OMS Internal Components** | `application/oms/_internal/` | `brokers/common/oms/_internal/` | `application/oms/_internal/` | 🔴 Critical |
| `reentrancy_guard.py` | `application/oms/_internal/reentrancy_guard.py` | `brokers/common/oms/_internal/reentrancy_guard.py` | `domain/guards/reentrancy.py` | 🟠 High |
| `normalize_symbol()` | `datalake/symbols.py:17` | `datalake/normalize.py:84` | `domain/symbols.py` | 🟠 High |
| **Connection Settings Pattern** | `brokers/common/settings.py` | `brokers/dhan/settings.py` | `brokers/common/settings.py` (base) | 🟡 Medium |
| **Connection Settings Pattern** | `brokers/common/settings.py` | `brokers/upstox/auth/config.py` | `brokers/common/settings.py` (base) | 🟡 Medium |
| **Endpoint Registry** | `endpoints.py` (root) | Implicitly duplicated in each broker's `_resolve_*` methods | `brokers/common/endpoints/` | 🔴 Critical |
| **Index Symbol Mapping** | `indices.py` (root) | Potentially in `domain/constants/` or broker resolvers | `domain/market_data/indices.py` | 🟠 High |
| **Secrets Access** | `secrets_manager.py` (root) | `brokers/common/auth/environment_bootstrap.py` | `infrastructure/secrets/` | 🟠 High |
| **Test Fixtures** | `conftest.py` (root) | `tests/conftest.py` + per-module `conftest.py` | Co-located with modules | 🟡 Medium |

### Deep Dive: OMS Duplication (🔴 Critical)

```
application/oms/_internal/          brokers/common/oms/_internal/
├── __init__.py                     ├── __init__.py
├── loss_circuit_breaker.py         ├── (MISSING)
├── order_audit_logger.py           ├── (MISSING)
├── order_position_updater.py       ├── (MISSING)
├── order_state_validator.py        ├── (MISSING)
├── reentrancy_guard.py ───────┐    ├── reentrancy_guard.py
├── risk_manager.py             │    └── (differs from application version)
└── (3 unique files)            │
                            DIFFERENT IMPLEMENTATIONS
```

**Consequence**: Two teams (application vs broker infrastructure) maintain separate OMS logic. Changes to one won't propagate to the other. Production risk: order validation could pass in one path and fail in another.

**Prescription**: Consolidate into `application/oms/_internal/` as the single OMS implementation. If broker-specific OMS behaviour is needed, use a strategy pattern with a protocol defined in `domain/oms/`.

---

## 4. Detailed Findings

---
🔴 [CRITICAL] SECURITY INCIDENT — REAL CREDENTIALS IN REPOSITORY
Location: `.env.local` (40 lines, committed to git)
Organisation Concern: Secrets in Repository
Diagnosis: `.env.local` contains live Dhan and Upstox access tokens, API keys, client IDs, PINs, and TOTP secrets — anyone with repository access can authenticate as the trading account holder and place real orders.
Prescription: 1. IMMEDIATELY rotate ALL credentials in `.env.local`. 2. Add `.env.local` to `.gitignore` if not already present (verify with `git check-ignore .env.local`). 3. Run `git filter-branch` or BFG Repo-Cleaner to purge credentials from git history. 4. Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, or at minimum git-crypt) for credential distribution. 5. Replace `.env.local` with `.env.template` containing only placeholder values.
Effort: S (credential rotation) + M (history cleanup)
---

---
🔴 [CRITICAL] ROOT-LEVEL GOD MODULES BYPASS ALL ARCHITECTURAL BOUNDARIES
Location: `endpoints.py` (452 lines), `indices.py` (408 lines), `secrets_manager.py` (55 lines) at repository root
Organisation Concern: Hidden Intent + Dependency Violation
Diagnosis: Three substantial modules (915 total lines) live at the repository root and are imported directly by broker adapters (`brokers/dhan/http_client.py:from endpoints import Dhan`, `brokers/upstox/gateway.py:from indices import index_upstox_key`, `brokers/upstox/auth/config.py:from secrets_manager import SecretsManager`), creating implicit global dependencies that bypass the `brokers/common/` abstraction layer and make it impossible to swap or mock these concerns independently.
Prescription: Move `endpoints.py` → `brokers/common/endpoints/__init__.py` (split Dhan/Upstox into submodules). Move `indices.py` → `domain/market_data/indices.py` (index metadata is domain knowledge, not infrastructure). Move `secrets_manager.py` → `infrastructure/secrets/manager.py`. Update all imports via automated refactoring (e.g., `rope` or `ruff --fix`).
Effort: M
---

---
🔴 [CRITICAL] DUPLICATE OMS IMPLEMENTATIONS
Location: `application/oms/_internal/` (6 files) vs `brokers/common/oms/_internal/` (2 files with different content)
Organisation Concern: Duplicate Code + Wrong Ownership
Diagnosis: Order Management System logic exists in two separate locations with divergent implementations — `application/oms/_internal/` has 6 files including risk management and audit logging, while `brokers/common/oms/_internal/` has a different `reentrancy_guard.py` and missing critical files, creating a split-brain scenario where order processing behaviour depends on which import path is taken.
Prescription: 1. Consolidate all OMS logic into `application/oms/_internal/` (the application layer owns order processing use cases). 2. Remove `brokers/common/oms/_internal/` entirely. 3. If broker-specific order behaviour is needed, define a protocol in `domain/oms/protocols.py` and implement it in each broker adapter. 4. Update import-linter contract to forbid `brokers/common/oms/`.
Effort: M
---

---
🔴 [CRITICAL] BROKER ADAPTERS IMPORT ROOT-LEVEL FILES
Location: `brokers/dhan/http_client.py:1`, `brokers/dhan/orders.py:1`, `brokers/dhan/settings.py:1`, `brokers/upstox/gateway.py`, `brokers/upstox/auth/urls.py:1`, `brokers/upstox/market_data/futures.py`
Organisation Concern: Dependency Violation
Diagnosis: Broker adapters import from root-level `endpoints.py`, `indices.py`, and `secrets_manager.py` instead of going through `brokers/common/` abstractions, creating 16+ direct root imports that bypass the adapter pattern and make it impossible to run import-linter contracts effectively (hence the 10 ignored imports in `.import-linter.ini`).
Prescription: After relocating root-level files to proper modules (Finding #2), update all broker imports:
```python
# BEFORE (🔴 violation):
from endpoints import Dhan
from indices import is_index
from secrets_manager import SecretsManager

# AFTER (✅ correct):
from brokers.common.endpoints import DhanEndpoints
from domain.market_data.indices import is_index
from infrastructure.secrets.manager import SecretsManager
```
Effort: M
---

---
🔴 [CRITICAL] RUNTIME STATE FILES COMMITTED TO REPOSITORY
Location: `runtime/dhan-token-state.json`, `runtime/dhan-totp-cooldown.json`, `runtime/dead_letter.sqlite`
Organisation Concern: Hidden Intent + Configuration & Environment
Diagnosis: Runtime-generated state files (token state, TOTP cooldown tracking, dead-letter queue SQLite database) are committed to the repository, mixing ephemeral runtime data with source code and creating merge conflicts, stale state, and potential credential leakage (token state files may contain refresh tokens).
Prescription: 1. Add `runtime/*.json`, `runtime/*.sqlite` to `.gitignore`. 2. Move runtime state to a proper runtime directory outside the repository (e.g., `~/.tradexv2/runtime/` or `/var/lib/tradexv2/`). 3. Document the runtime directory structure in `docs/RUNTIME.md`. 4. Add a `runtime/.gitkeep` to preserve the directory structure for development.
Effort: S
---

---
🟠 [HIGH] BROKERS/COMMON IS A GOD MODULE (162 FILES, 55 DIRECTORIES)
Location: `brokers/common/` — 162 `.py` files, 55 subdirectories
Organisation Concern: Shared Library Misuse
Diagnosis: `brokers/common/` has grown to 162 Python files across 55 subdirectories including adapters, api, auth, connection, contracts, core, extensions, gateway, historical, logging, mapper, market_data, oms, observability, options, orders, reconciliation, resilience, retry, risk, services, settings, streaming, tests, types, utils, validation, websocket — this violates the "minimal, stable" shared library principle and creates a catch-all for anything the author didn't know where to place.
Prescription: Decompose `brokers/common/` into focused packages:
```
brokers/
├── core/                    # Abstract interfaces (gateway, factory, ports)
│   ├── gateway.py          # MarketDataGateway, BrokerGateway protocols
│   ├── factory.py          # BrokerProviderFactory
│   └── broker_port.py      # Broker port interfaces
├── shared/                  # Stable shared utilities (< 20 files)
│   ├── auth/               # Token management, TOTP
│   ├── resilience/         # Circuit breaker, retry, rate limiter
│   └── settings.py         # Base settings classes
├── dhan/                   # Dhan adapter (imports from brokers/core/)
├── upstox/                 # Upstox adapter (imports from brokers/core/)
└── paper/                  # Paper trading adapter
```
Delete `brokers/common/oms/` (moved to application). Delete `brokers/common/utils/` if it exists. Each remaining subdirectory must have a documented public API in `__init__.py`.
Effort: L
---

---
🟠 [HIGH] DUPLICATE `normalize_symbol()` FUNCTIONS
Location: `datalake/symbols.py:17` and `datalake/normalize.py:84`
Organisation Concern: Duplicate Code
Diagnosis: Two functions named `normalize_symbol()` exist in the same package (`datalake/`), creating ambiguity about which is canonical and risking inconsistent symbol normalization across the codebase (different normalisation results for the same input would cause data integrity issues in the datalake).
Prescription: 1. Compare both implementations to determine the canonical version. 2. Keep the canonical version in `datalake/symbols.py`. 3. Remove `datalake/normalize.py` or rename it to `datalake/normalization.py` with non-colliding function names. 4. Add an import-linter contract forbidding duplicate function names within a package.
Effort: S
---

---
🟠 [HIGH] EMPTY `__init__.py` FILES INDICATE MISSING MODULE BOUNDARIES
Location: 30+ `__init__.py` files in `brokers/upstox/` with ≤ 3 lines (no `__all__` declaration)
Organisation Concern: Module Boundary + Naming
Diagnosis: Modules like `brokers/upstox/reconciliation/__init__.py` (3 lines), `brokers/upstox/fundamentals/__init__.py` (3 lines), `brokers/upstox/ipo/__init__.py` (3 lines) have no `__all__` declaration, meaning Python's default import behaviour exposes everything — this makes the public API implicit and fragile, as any internal function can be imported from outside the module without the module owner's knowledge.
Prescription: Every `__init__.py` must explicitly declare `__all__`:
```python
# brokers/upstox/reconciliation/__init__.py
"""Upstox reconciliation — matches broker positions with internal records."""
from brokers.upstox.reconciliation.position_matcher import PositionMatcher

__all__ = ["PositionMatcher"]
```
Run `ruff check --select=ICN` to enforce import conventions. Add a pre-commit hook that fails if `__init__.py` lacks `__all__`.
Effort: S
---

---
🟠 [HIGH] MARKET_DATA/ OVERLAPS WITH BROKERS/*/MARKET_DATA/
Location: `market_data/` (20 directories) vs `brokers/dhan/market_data/`, `brokers/upstox/market_data/`, `brokers/common/market_data/`
Organisation Concern: Duplicate Code + Wrong Ownership
Diagnosis: A top-level `market_data/` directory exists alongside broker-specific `market_data/` subdirectories, creating confusion about where market data logic belongs — the top-level directory likely contains broker-agnostic market data abstractions that should be in `domain/market_data/` or `brokers/common/market_data/`.
Prescription: 1. Audit `market_data/` contents. 2. Move domain-level abstractions to `domain/market_data/`. 3. Move shared implementations to `brokers/core/market_data/`. 4. Remove top-level `market_data/` directory. 5. Update all imports.
Effort: M
---

---
🟠 [HIGH] API_SERVER.PY IS AN ORPHAN ENTRY POINT
Location: `api_server.py` (47 lines) at repository root
Organisation Concern: Hidden Intent
Diagnosis: `api_server.py` is a launcher script that imports from `api/`, `brokers/common/`, and `runtime/` but lives at the repository root where it has no clear ownership and is easily missed by developers looking for the application entry point.
Prescription: Move to `entry_points/api_server.py` or `cli/commands/serve.py`. Better yet, make it a proper CLI subcommand:
```python
# cli/commands/serve.py
import click

@click.command()
def serve():
    """Start the TradeXV2 API server."""
    from api.main import create_app
    from runtime.api_bootstrap import initialize_api_services
    # ... launch logic
```
Effort: S
---

---
🟠 [HIGH] CONFTest.PY AT ROOT IS TOO LARGE AND MIXED CONCERN
Location: `conftest.py` (166 lines) at repository root
Organisation Concern: Hidden Intent + Wrong Ownership
Diagnosis: Root `conftest.py` contains SDK compatibility shims (`_ensure_dhanhq_sdk_aliases`) that are broker-specific, violating the principle that root conftest should only hold truly cross-cutting fixtures — broker-specific shims belong in `brokers/dhan/tests/conftest.py`.
Prescription: 1. Move `_ensure_dhanhq_sdk_aliases()` to `brokers/dhan/tests/conftest.py`. 2. Keep only truly cross-cutting fixtures in root `conftest.py`. 3. Add a comment at the top of root `conftest.py` documenting what belongs there vs. in module-specific conftest files.
Effort: S
---

---
🟡 [MEDIUM] APPLICATION/__INIT__.PY HAS EMPTY __ALL__
Location: `application/__init__.py` (4 lines)
Organisation Concern: Module Boundary
Diagnosis: `application/__init__.py` declares `__all__: list[str] = []` — an empty public API — which means the application layer has no explicitly exported interface, forcing consumers to import internal modules directly (`from application.oms.service import OMS`) and making refactoring unsafe.
Prescription: Define the public API:
```python
"""Application layer — use cases, OMS, execution, and trading orchestration."""
from application.oms.service import OMS
from application.execution.service import ExecutionService
from application.trading.orchestrator import TradingOrchestrator

__all__ = ["OMS", "ExecutionService", "TradingOrchestrator"]
```
Effort: S
---

---
🟡 [MEDIUM] CONFIGURATION SCATTERED ACROSS 4 LOCATIONS
Location: `.env.local`, `config/schema.py`, `domain/constants/defaults.py`, `runtime/production_config.py`
Organisation Concern: Configuration & Environment
Diagnosis: Configuration is spread across environment files, a Pydantic schema, domain constants, and runtime configuration — there is no single canonical source of truth for configuration, making it unclear where to add new settings and risking inconsistent defaults.
Prescription: 1. Create `config/settings.py` with a single `TradeXV2Settings` Pydantic BaseSettings class that loads from environment. 2. Move `domain/constants/defaults.py` → `config/defaults.py`. 3. Remove `runtime/production_config.py` (replace with environment-specific config files). 4. Document the configuration hierarchy in `docs/CONFIGURATION.md`.
Effort: M
---

---
🟡 [MEDIUM] DUAL VIRTUAL ENVIRONMENTS CREATE CONFUSION
Location: `.venv/` and `venv/` both exist at repository root
Organisation Concern: Naming + Hidden Intent
Diagnosis: Two virtual environment directories exist (`.venv/` and `venv/`), suggesting inconsistent tooling usage (uv vs venv vs virtualenv) and creating confusion about which environment is canonical for development.
Prescription: 1. Standardise on `.venv/` (uv default). 2. Add `venv/` to `.gitignore`. 3. Remove `venv/` after confirming it's not needed. 4. Document the standard development setup in `CONTRIBUTING.md`.
Effort: S
---

---
🟡 [MEDIUM] DATA/ OVERLAPS WITH DATALAKE/
Location: `data/` (4 subdirectories) vs `datalake/` (34 subdirectories)
Organisation Concern: Duplicate Code + Hidden Intent
Diagnosis: A top-level `data/` directory exists alongside `datalake/`, creating ambiguity about where data-related code belongs — `data/` appears to be a legacy or unused directory that hasn't been cleaned up.
Prescription: 1. Audit `data/` contents. 2. Move any active code to `datalake/`. 3. Remove `data/` if empty or legacy. 4. If `data/` contains test fixtures, rename to `tests/fixtures/data/`.
Effort: S
---

---
🟡 [MEDIUM] SCRIPTS/ DIRECTORY HAS NO CATEGORISATION
Location: `scripts/` — 27 Python files and shell scripts with no subdirectory structure
Organisation Concern: Hidden Intent + Wrong Ownership
Diagnosis: 27 scripts in a flat directory (`audit_broker_methods.py`, `clean_indices.py`, `generate_dependency_graph.py`, `test_totp_flow.py`, etc.) mix one-off utilities, CI helpers, test scripts, and migration tools — there's no way to determine ownership, purpose, or which are safe to delete.
Prescription: Categorise scripts into subdirectories:
```
scripts/
├── ci/             # CI/CD helpers (production_certification.py, etc.)
├── migration/      # One-time migrations (migrate_shim_imports.py, etc.)
├── diagnostics/    # Debugging and auditing (audit_broker_methods.py, etc.)
├── test/           # Test helpers (test_totp_flow.py, etc.)
└── tools/          # Developer utilities (generate_dependency_graph.py, etc.)
```
Effort: S
---

---
🟡 [MEDIUM] DOMAIN/CONSTANTS/ MIXES CONFIGURATION WITH DOMAIN KNOWLEDGE
Location: `domain/constants/defaults.py`, `domain/constants/timeouts.py`, `domain/constants/resilience.py`
Organisation Concern: Dependency Violation
Diagnosis: `domain/constants/` contains operational configuration (timeouts, resilience settings, observability config) that changes with deployment environment — domain layer should contain only business invariants, not tunable operational parameters.
Prescription: 1. Keep truly domain constants in `domain/constants/` (exchange codes, order types, market rules). 2. Move operational configuration to `config/`: `config/defaults.py`, `config/timeouts.py`, `config/resilience.py`. 3. Domain should import from `config/` through application layer injection, not directly.
Effort: M
---

---
🟢 [LOW] TESTS/ AND CO-LOCATED TESTS CREATE DUAL TEST LOCATIONS
Location: `tests/` (41 subdirectories) + `brokers/dhan/tests/`, `brokers/upstox/tests/`, `brokers/common/*/tests/`
Organisation Concern: Naming
Diagnosis: Tests exist in two patterns: co-located within modules (`brokers/dhan/tests/`) and centralised (`tests/`) — while both patterns are valid, having both without clear convention creates confusion about where to put new tests.
Prescription: Choose one pattern and enforce it. Recommended: co-located tests (`module/tests/`) for module-owned tests, `tests/` only for cross-cutting integration tests. Document in `CONTRIBUTING.md`.
Effort: S
---

---
🟢 [LOW] TRADEX SHELL SCRIPT ENTRY POINT IS UNDERSPECIFIED
Location: `tradex` (772 bytes, executable shell script at repository root)
Organisation Concern: Hidden Intent
Diagnosis: `tradex` is an executable shell script at the repository root with no documentation about its purpose, making it an undocumented entry point that developers may bypass or duplicate.
Prescription: 1. If it's the CLI entry point, move to `cli/entry.sh` or replace with a Python entry point in `pyproject.toml`. 2. If it's a development wrapper, document its purpose in `docs/DEVELOPMENT.md`.
Effort: S
---

---
🟢 [LOW] ARCHIVE/ DIRECTORY SHOULD BE DOCUMENTED
Location: `archive/` (3 subdirectories)
Organisation Concern: Hidden Intent
Diagnosis: An `archive/` directory exists with no documentation about what's archived, why, or whether it should be referenced by new development.
Prescription: Add `archive/README.md` documenting: 1. What was archived. 2. When and why. 3. Whether code should be resurrected or deleted.
Effort: S
---

---

## 5. Proposed Clean Structure

Following Uncle Bob's screaming architecture and Dr. Venkat's cohesion/coupling principles:

```
tradexv2/
│
├── README.md                         # Project overview
├── CONTRIBUTING.md                   # Development guidelines
├── CHANGELOG.md                      # Version history
├── SECURITY.md                       # Security policy
├── pyproject.toml                    # Build config, dependencies, entry points
├── .gitignore                        # Git exclusions
├── .import-linter.ini                # Architecture enforcement
├── .pre-commit-config.yaml           # Pre-commit hooks
│
├── .env.example                      # ✅ Template only (NO real values)
├── .env.upstox                       # ⚠️ Merge into .env.example or remove
│
├── entry_points/                     # 🆕 ALL application entry points
│   ├── __init__.py
│   ├── api_server.py                 # ← moved from root
│   ├── cli.py                        # ← tradex shell script replacement
│   └── scheduler.py                  # ← if scheduled jobs exist
│
├── trading/                          # 🆕 Top-level = BUSINESS CAPABILITY
│   │   """Core trading operations — orders, positions, P&L"""
│   ├── __init__.py
│   ├── domain/                       # 🆕 Trading domain (entities, value objects)
│   │   ├── __init__.py
│   │   ├── entities.py               # Order, Position, Trade, Balance
│   │   ├── enums.py                  # Side, OrderType, ProductType, Validity
│   │   ├── events.py                 # OrderPlaced, PositionUpdated, etc.
│   │   ├── exceptions.py             # OrderValidationError, InsufficientFunds
│   │   ├── protocols.py              # BrokerGateway, MarketDataProvider
│   │   └── value_objects.py          # Symbol, Quantity, Price
│   │
│   ├── application/                  # 🆕 Trading use cases
│   │   ├── __init__.py
│   │   ├── oms/                      # Order Management System
│   │   │   ├── __init__.py           # With __all__
│   │   │   ├── service.py            # OMS orchestration
│   │   │   ├── validators.py         # Order validation
│   │   │   ├── guards.py             # Reentrancy, circuit breaker
│   │   │   ├── risk_manager.py       # Risk checks
│   │   │   └── audit_logger.py       # Order audit trail
│   │   ├── execution/                # Order execution
│   │   │   ├── __init__.py
│   │   │   └── service.py
│   │   └── trading/                  # Trading orchestration
│   │       ├── __init__.py
│   │       └── orchestrator.py
│   │
│   ├── brokers/                      # 🆕 Broker adapters
│   │   ├── __init__.py
│   │   ├── core/                     # ← decomposed from brokers/common/
│   │   │   ├── __init__.py           # __all__ with public API
│   │   │   ├── gateway.py            # BrokerGateway protocol
│   │   │   ├── factory.py            # BrokerProviderFactory
│   │   │   ├── endpoints/            # ← moved from root endpoints.py
│   │   │   │   ├── __init__.py
│   │   │   │   ├── dhan.py
│   │   │   │   └── upstox.py
│   │   │   ├── auth/                 # Token management
│   │   │   │   ├── __init__.py
│   │   │   │   ├── totp.py
│   │   │   │   └── jwt.py
│   │   │   └── resilience/           # Circuit breaker, retry, rate limiter
│   │   │       ├── __init__.py
│   │   │       ├── circuit_breaker.py
│   │   │       ├── retry.py
│   │   │       └── rate_limiter.py
│   │   │
│   │   ├── dhan/                     # Dhan adapter
│   │   │   ├── __init__.py           # __all__ with public API
│   │   │   ├── gateway.py
│   │   │   ├── http_client.py
│   │   │   ├── market_data/
│   │   │   ├── orders/
│   │   │   ├── auth/
│   │   │   └── tests/
│   │   │
│   │   ├── upstox/                   # Upstox adapter
│   │   │   ├── __init__.py           # __all__ with public API
│   │   │   ├── gateway.py
│   │   │   ├── http_client.py
│   │   │   ├── market_data/
│   │   │   ├── orders/
│   │   │   ├── auth/
│   │   │   └── tests/
│   │   │
│   │   └── paper/                    # Paper trading (mock)
│   │       ├── __init__.py
│   │       ├── gateway.py
│   │       └── tests/
│   │
│   └── tests/                        # Co-located tests
│       ├── unit/
│       ├── contract/
│       └── integration/
│
├── market_analysis/                  # 🆕 Renamed from analytics/
│   │   """Quantitative analysis — scanners, backtests, strategies"""
│   ├── __init__.py
│   ├── scanner/
│   ├── backtest/
│   ├── strategy/
│   ├── replay/
│   └── tests/
│
├── data_platform/                    # 🆕 Renamed from datalake/
│   │   """Data persistence, retrieval, and validation"""
│   ├── __init__.py
│   ├── symbols.py                    # Canonical normalize_symbol()
│   ├── storage/
│   ├── api/
│   ├── gateway.py
│   └── tests/
│
├── platform_api/                     # 🆕 Renamed from api/
│   │   """External HTTP API (FastAPI/Flask)"""
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── routes/
│   └── tests/
│
├── cli/                              # ✅ Keep — business capability
│   │   """Command-line interface"""
│   ├── __init__.py
│   ├── commands/
│   │   ├── serve.py                  # ← api_server.py becomes a command
│   │   ├── trade.py
│   │   └── analyze.py
│   └── tests/
│
├── infrastructure/                   # ✅ Keep — infrastructure layer
│   │   """External services — notifications, logging, monitoring"""
│   ├── __init__.py
│   ├── secrets/                      # ← moved from root secrets_manager.py
│   │   ├── __init__.py
│   │   └── manager.py
│   ├── logging/
│   ├── monitoring/
│   └── tests/
│
├── config/                           # ✅ Keep — configuration
│   │   """All configuration — one canonical source"""
│   ├── __init__.py
│   ├── schema.py                     # Pydantic settings
│   ├── defaults.py                   # ← from domain/constants/defaults.py
│   ├── timeouts.py                   # ← from domain/constants/timeouts.py
│   └── resilience.py                 # ← from domain/constants/resilience.py
│
├── runtime/                          # 🆕 Runtime state and bootstrap
│   │   """Application bootstrap and runtime state (NOT committed to git)"""
│   ├── __init__.py
│   ├── api_bootstrap.py
│   ├── trading_runtime_factory.py
│   ├── .gitkeep                      # Preserve directory structure
│   └── .gitignore                    # *.json, *.sqlite
│
├── scripts/                          # ✅ Categorized
│   ├── ci/
│   ├── migration/
│   ├── diagnostics/
│   ├── test/
│   └── tools/
│
├── frontend/                         # ✅ Keep — separate UI concern
├── docs/                             # ✅ Keep — documentation
│   ├── ARCHITECTURE.md
│   ├── ARCHITECTURE_V2.md
│   ├── ARCHITECTURE_V3.md            # ← This document
│   ├── CONFIGURATION.md
│   ├── RUNTIME.md
│   └── DEVELOPMENT.md
│
└── .github/
    ├── CODEOWNERS
    └── workflows/
```

### Design Rationale

1. **`trading/` as top-level business capability**: The system is a trading platform. `trading/` screams that intent. It contains the domain model, use cases, and broker adapters — everything related to executing trades.

2. **Dependency direction preserved**: `trading/domain/` ← `trading/application/` ← `trading/brokers/` ← `infrastructure/`. Domain never imports from infrastructure.

3. **Entry points explicit**: `entry_points/` contains all application launchers. No more orphan root-level Python files.

4. **Shared code minimal**: `trading/brokers/core/` contains only stable abstractions (protocols, factories, resilience patterns) — not business logic.

5. **Configuration canonical**: All configuration in `config/`, loaded through a single Pydantic settings class. Environment-specific values via environment variables, not files.

6. **Tests co-located**: Each module has its own `tests/` directory. Central `tests/` only for cross-cutting integration tests.

---

## 6. Migration Plan

Ordered by safety (non-breaking moves first) then impact.

### Phase 1: Security Emergency (Day 1)

| Step | Action | Risk | Mitigation |
|------|--------|------|------------|
| 1.1 | Rotate ALL credentials in `.env.local` | HIGH — invalidates live tokens | Have backup credentials ready |
| 1.2 | Add `.env.local` to `.gitignore` | NONE | Verify with `git check-ignore` |
| 1.3 | Purge credentials from git history using BFG Repo-Cleaner | HIGH — rewrites history | Do on a branch, coordinate with team |
| 1.4 | Remove runtime state files from git (`runtime/*.json`, `runtime/*.sqlite`) | LOW — runtime will regenerate | Add to `.gitignore` first |

### Phase 2: Non-Breaking Moves (Days 2-3)

| Step | Action | Breaks | How to Update |
|------|--------|--------|---------------|
| 2.1 | Move `scripts/` → `scripts/{ci,migration,diagnostics,test,tools}/` | NONE — internal scripts only | Update CI/CD references |
| 2.2 | Move `conftest.py` broker-specific fixtures → `brokers/dhan/tests/conftest.py` | NONE — test fixtures only | Update pytest imports |
| 2.3 | Add `__all__` to all empty `__init__.py` files | NONE — additive change | Run import-linter to verify |
| 2.4 | Consolidate `normalize_symbol()` → `datalake/symbols.py` | LOW — if callers import from `normalize.py` | Update imports, add deprecation warning |

### Phase 3: Module Relocation (Days 4-7)

| Step | Action | Breaks | How to Update |
|------|--------|--------|---------------|
| 3.1 | Move `endpoints.py` → `brokers/common/endpoints/__init__.py` | HIGH — 16+ import sites | Automated search-replace + manual review |
| 3.2 | Move `indices.py` → `domain/market_data/indices.py` | MEDIUM — 8+ import sites | Automated search-replace + manual review |
| 3.3 | Move `secrets_manager.py` → `infrastructure/secrets/manager.py` | MEDIUM — 4+ import sites | Automated search-replace + manual review |
| 3.4 | Move `api_server.py` → `entry_points/api_server.py` | LOW — single entry point | Update launch scripts, Docker configs |
| 3.5 | Move `conftest.py` → `tests/conftest.py` | LOW — pytest auto-discovers | Verify pytest discovery |

### Phase 4: Structural Refactoring (Days 8-14)

| Step | Action | Breaks | How to Update |
|------|--------|--------|---------------|
| 4.1 | Consolidate OMS: merge `brokers/common/oms/` → `application/oms/_internal/` | HIGH — OMS is critical path | Extensive testing, feature flags |
| 4.2 | Decompose `brokers/common/` → `brokers/core/` + `brokers/shared/` | HIGH — 162 files affected | Incremental: one subdirectory at a time |
| 4.3 | Resolve `market_data/` vs `datalake/` overlap | MEDIUM — depends on audit results | Merge or delete based on usage |
| 4.4 | Move domain config constants → `config/` | MEDIUM — domain imports | Inject through application layer |
| 4.5 | Standardise virtual environment to `.venv/` | LOW — dev environment only | Update CONTRIBUTING.md |

### Phase 5: Cleanup (Days 15-16)

| Step | Action | Breaks | How to Update |
|------|--------|--------|---------------|
| 5.1 | Remove `data/` directory (after audit) | NONE if unused | Verify no imports |
| 5.2 | Remove `venv/` directory | NONE — dev environment | Confirm `.venv/` works |
| 5.3 | Document `archive/` | NONE | Add README.md |
| 5.4 | Replace `tradex` shell script with Python entry point | LOW — update symlinks | Update `pyproject.toml` entry points |

### Import Update Strategy

For each relocation, use this pattern:

```bash
# 1. Find all import sites
grep -r "from endpoints import\|from indices import\|from secrets_manager import" --include="*.py"

# 2. Update with sed (example for endpoints)
find . -name "*.py" -exec sed -i '' \
  's/from endpoints import/from tradexv2.brokers.core.endpoints import/g' {} +

# 3. Run import-linter to verify
lint-imports

# 4. Run tests
pytest -x

# 5. Commit with descriptive message
git commit -m "refactor: move endpoints.py to brokers/core/endpoints/
  
  - Brokers now import from canonical location
  - Removes root-level orphan module
  - All 16 import sites updated"
```

---

## 7. Remediation Roadmap

Ordered: 🔴 → 🟠 → 🟡 → 🟢 | effort (S/M/L) per item

| Priority | Finding | Severity | Effort | Owner | Status |
|----------|---------|----------|--------|-------|--------|
| 1 | Rotate credentials + purge from git history | 🔴 | S | @lead-engineer @security | ⏳ PENDING |
| 2 | Relocate `endpoints.py` to `brokers/common/endpoints/` | 🔴 | M | @lead-engineer | ⏳ PENDING |
| 3 | Relocate `indices.py` to `domain/market_data/indices.py` | 🔴 | M | @lead-engineer | ⏳ PENDING |
| 4 | Relocate `secrets_manager.py` to `infrastructure/secrets/` | 🔴 | S | @lead-engineer | ⏳ PENDING |
| 5 | Consolidate duplicate OMS implementations | 🔴 | M | @lead-engineer @quant-lead | ⏳ PENDING |
| 6 | Remove runtime state files from git | 🔴 | S | @sre | ⏳ PENDING |
| 7 | Decompose `brokers/common/` God module | �� | L | @lead-engineer | ⏳ PENDING |
| 8 | Add `__all__` to all empty `__init__.py` | 🟠 | S | @lead-engineer | ⏳ PENDING |
| 9 | Resolve `normalize_symbol()` duplication | 🟠 | S | @lead-engineer | ⏳ PENDING |
| 10 | Resolve `market_data/` overlap | 🟠 | M | @lead-engineer @quant-lead | ⏳ PENDING |
| 11 | Move `api_server.py` to entry_points/ | 🟠 | S | @lead-engineer | ⏳ PENDING |
| 12 | Split root `conftest.py` | 🟠 | S | @qa-lead | ⏳ PENDING |
| 13 | Populate `application/__all__` | 🟡 | S | @lead-engineer | ⏳ PENDING |
| 14 | Consolidate configuration to `config/` | 🟡 | M | @lead-engineer | ⏳ PENDING |
| 15 | Standardise virtual environment | 🟡 | S | @sre | ⏳ PENDING |
| 16 | Resolve `data/` vs `datalake/` overlap | 🟡 | S | @lead-engineer | ⏳ PENDING |
| 17 | Categorise `scripts/` directory | 🟡 | S | @lead-engineer | ⏳ PENDING |
| 18 | Move domain config constants to `config/` | 🟡 | M | @lead-engineer | ⏳ PENDING |
| 19 | Standardise test locations | 🟢 | S | @qa-lead | ⏳ PENDING |
| 20 | Replace `tradex` shell script | 🟢 | S | @lead-engineer | ⏳ PENDING |
| 21 | Document `archive/` | 🟢 | S | @lead-engineer | ⏳ PENDING |

### Effort Legend
- **S** (Small): < 2 hours, single developer, low risk
- **M** (Medium): 2-8 hours, may affect multiple files, moderate risk
- **L** (Large): 1-3 days, affects many modules, requires coordination

---

## 8. Architecture Debt Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Dependency Violations | 2 | 1 | 1 | 0 | 4 |
| Security | 1 | 0 | 0 | 0 | 1 |
| Duplicate Code | 1 | 2 | 0 | 0 | 3 |
| Module Boundaries | 0 | 2 | 2 | 0 | 4 |
| Shared Library Misuse | 0 | 1 | 0 | 0 | 1 |
| Configuration & Environment | 1 | 0 | 2 | 0 | 3 |
| Naming & Organisation | 0 | 2 | 2 | 3 | 7 |
| **TOTAL** | **5** | **8** | **7** | **3** | **23** |

---

## 9. Uncle Bob + Dr. Venkat Principle Checklist

| Principle | Status | Evidence |
|-----------|--------|----------|
| **Screaming Architecture** | 🔴 FAIL | Top-level folders are technical layers (`domain/`, `application/`), not business capabilities (`trading/`, `analysis/`) |
| **Dependency Rule** | ⚠️ PARTIAL | Domain is clean ✅, but broker adapters import root-level files 🔴 |
| **Single Responsibility per Module** | 🔴 FAIL | `brokers/common/` has 162 files doing everything |
| **Explicit Public API** | 🔴 FAIL | 30+ `__init__.py` files with no `__all__` |
| **No Cyclic Dependencies** | 🔴 FAIL | Root-level files create implicit cycles |
| **Minimal Shared Code** | 🔴 FAIL | `brokers/common/` is a God module |
| **Configuration Externalised** | 🔴 FAIL | Credentials in repository, config scattered |
| **Tests Findable** | 🟡 PARTIAL | Dual test locations without convention |
| **Entry Points Explicit** | 🔴 FAIL | Orphan root-level launchers |
| **No Secrets in Repository** | 🔴 FAIL | Real credentials committed |

---

## 10. Next Steps

### Immediate (fix this week) 🔴
- [ ] Rotate ALL credentials exposed in `.env.local`
- [ ] Add `.env.local` to `.gitignore` and purge from git history
- [ ] Remove runtime state files (`*.json`, `*.sqlite`) from git
- [ ] Move `endpoints.py`, `indices.py`, `secrets_manager.py` to proper locations
- [ ] Consolidate duplicate OMS implementations

### Short-term (next sprint) 🟠
- [ ] Add `__all__` to all module `__init__.py` files
- [ ] Resolve `normalize_symbol()` duplication
- [ ] Move `api_server.py` to `entry_points/`
- [ ] Split root `conftest.py` broker-specific fixtures
- [ ] Begin decomposing `brokers/common/` God module
- [ ] Resolve `market_data/` overlap

### Medium-term (next quarter) 🟡
- [ ] Complete `brokers/common/` decomposition
- [ ] Consolidate configuration to single `config/` package
- [ ] Move domain config constants to `config/`
- [ ] Standardise test location convention
- [ ] Categorise `scripts/` directory
- [ ] Resolve `data/` vs `datalake/` overlap
- [ ] Standardise virtual environment

### Ongoing 💡
- [ ] Enforce architecture contracts in CI via import-linter
- [ ] Add pre-commit hook requiring `__all__` in `__init__.py`
- [ ] Document module ownership in CODEOWNERS
- [ ] Regular architecture review (monthly)

---

## Appendix A: Import-Linter Contract Status

Current `.import-linter.ini` enforces 10 contracts with **10 ignored imports**:

| Contract | Ignored Imports | Reason |
|----------|----------------|--------|
| `brokers-common-independence` | 4 | Tests in `brokers.common.core.tests` import broker-specific code |
| `no-upstox-in-dhan` | 1 | Contract tests import `brokers.upstox.auth.jwt_expiry` |
| `application-broker-isolation` | 5 | Tests import `brokers.paper`, `brokers.dhan`, `brokers.common.resilience` |

**Recommendation**: After relocating root-level files and consolidating OMS, these ignored imports should be eliminated. Tests should use mocks or test doubles, not real broker implementations.

---

## Appendix B: File Count Summary

| Module | Python Files | Directories | Assessment |
|--------|-------------|-------------|------------|
| `domain/` | 66 | 10 | ✅ Well-scoped |
| `application/` | 70 | 5 | ✅ Well-scoped |
| `brokers/` | 441 | 55+ | 🔴 God module (common: 162 files) |
| `infrastructure/` | 22 | 4 | ✅ Well-scoped |
| `analytics/` | ~200 | 28 | ⚠️ Large but acceptable for quant code |
| `datalake/` | ~150 | 34 | ⚠️ Large, overlaps with `data/` |
| `cli/` | ~80 | 13 | ✅ Well-scoped |
| `api/` | ~40 | 14 | ✅ Well-scoped |
| `scripts/` | 27 | 0 | 🔴 Flat, uncategorized |
| `runtime/` | 7 | 1 | ⚠️ Contains runtime state files |
| **Root orphans** | 5 | 0 | 🔴 Must relocate |

---

## Appendix C: Security Incident Response

**IF YOU ARE READING THIS AND `.env.local` IS COMMITTED TO A SHARED REPOSITORY:**

1. **DO NOT** merge any new code until credentials are rotated.
2. **DO** assume all credentials in `.env.local` are compromised.
3. **DO** rotate credentials on ALL broker accounts (Dhan and Upstox).
4. **DO** audit broker account activity for unauthorised orders.
5. **DO** enable IP whitelisting on broker accounts if available.
6. **DO** use a proper secrets manager going forward.

This is not a configuration problem. This is a security incident.

---

*Document Version: 3.0*  
*Last Updated: 2026-06-25*  
*Author: Principal Software Architecture Auditor*  
*Reviewers: @lead-engineer, @quant-lead, @sre, @security*
