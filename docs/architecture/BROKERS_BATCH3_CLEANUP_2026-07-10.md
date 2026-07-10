# Batch 3 — Brokers Layout Cleanup (2026-07-10)

**Branch:** `refactor/structural-cleanup`  
**Constraint (from `docs/reports/BROKERS_EVOLUTION_PLAN.md`):** no Dhan/Upstox tree rewrite; gateways stay transport; residual `brokers.common` is intentional.

## Why this batch is small

Waves A–E already purged ~50 pure re-export shims under `brokers.common`. What remained for Batch 3 was **leftover husks** (directories with only `__pycache__` from deleted modules) plus **stale architecture exceptions / docstrings** that still named the dead paths.

Merging `dhan/` ↔ `upstox/` package layouts is **out of scope** (evolution plan). Those trees are large, live transport code, and different shapes on purpose.

## Inventory (post Wave E, pre this batch)

| Area | Status |
|------|--------|
| `brokers/common/auth, options, reconciliation, resilience, services` | Empty husks (`__pycache__` only) |
| `brokers/upstox/resilience` | Empty husk |
| `brokers/common` residual real code | `api/`, `oms/margin_provider`, `broker_capabilities` (thin domain re-export), `capabilities_validator`, `tick_validation`, `contracts/`, `tests/` |
| `brokers/dhan`, `brokers/upstox`, `brokers/paper` | Healthy broker packages — leave structure |
| `brokers/runtime/` | Token JSON process state — not a Python package; do not treat as BC |

## Actions taken

1. **Deleted husk dirs** (no source files, zero production imports):
   - `src/brokers/common/{auth,options,reconciliation,resilience,services}/`
   - `src/brokers/upstox/resilience/`
2. **Architecture fitness exceptions** — removed dead paths:
   - `src/brokers/common/resilience`
   - `src/brokers/common/services/download_engine.py`
   - `src/brokers/common/quota_scheduler.py`
   - `src/brokers/common/idempotency/*`
3. **Docstring fixes** so comments match canonical homes:
   - `infrastructure.auth.env_token` (not `brokers.common.auth`)
   - `domain.options.chain_normalizer` (not `brokers.common.options`)
   - Dhan reconciliation → `application.oms.reconciliation`

## What remains under `brokers.common` (intentional)

```
brokers/common/
  api/           # MarginProvider + SPI protocols used by Upstox adapters
  oms/           # BrokerMarginProvider only (not OMS core)
  contracts/     # Cross-broker certification suites
  tests/         # Shared broker tests
  broker_capabilities.py   # thin re-export → domain.capabilities
  capabilities_validator.py
  tick_validation.py
```

Do **not** add new re-export shims. Prefer `domain.*` / `infrastructure.*` / `application.*`.

## Explicitly held off

| Item | Why |
|------|-----|
| Align dhan/ vs upstox/ subpackage names | Tree rewrite; high blast radius |
| Move `brokers.common.api` protocols → `domain.ports` | Real callers in Upstox adapters; separate migration |
| Delete `broker_capabilities` re-export | Still imported by gateways/registry; keep until call sites migrate |
| `brokers/runtime` token files | Ops data; gitignore / not a layout BC |
| Single-file upstox subpackages (`ipo/`, `news/`, …) | Real client+adapter pairs; legitimate growth |

## Verification

```bash
venv/bin/python -m pytest tests/architecture/ tests/test_architecture.py src/brokers/common/tests/ -q
```

## Relation to domain Batch 1–2

Domain consolidation (~38 → 29 packages) landed first so broker import rewrites no longer chase dead `domain.composition` / `domain.utils` paths.
