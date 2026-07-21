# ADR-002: Strict layer dependency rule

- **Status:** Proposed
- **Date:** 2026-07-12
- **Deciders:** Architecture review

## Context
The `runtime/` integration layer imports concrete brokers directly
(`src/runtime/broker_infrastructure.py:10-39`, `broker_accessors.py:34-119`) and uses
string branching (`src/runtime/trading_runtime_factory.py:105`). This bypasses the
domain ports and makes the system broker-coupled (shotgun surgery). The current
import-linter contracts already carry `ignore_imports` exceptions that document these
violations.

## Decision
Adopt the dependency rule in `target-layering.md` §1 as a CI-enforced contract:
- `domain` → nothing inward.
- `application` → `domain` only.
- `infrastructure` → `domain` ports only.
- `runtime` → the ONLY layer that may import concrete brokers/plugins; selection by
  plugin registry, never by string equality scattered across modules.
- `interface` → `application` + `runtime`; never `brokers` directly.

Existing `runtime/` violations are tracked as temporary, time-boxed `ignore_imports`
exceptions, removed in Phase 5 (P5-3).

## Consequences
- Positive: broker-agnosticism becomes structurally enforced, not convention.
- Negative: `runtime/` must grow a small plugin-registry module; some factory code moves.
- Cost: existing exceptions must be cleaned before Phase 6.

## Validation
- import-linter contract in `pyproject.toml` reflects the rule; new violations fail CI.

## Status (implemented 2026-07-12)
- **Status:** Accepted.
- The rule is enforced by the import-linter suite in `pyproject.toml` (`[tool.importlinter]`).
  Most directions already had contracts (Domain independence, Infrastructure independence,
  Application broker isolation, Application->infrastructure separation, Runtime->interface block,
  Interface broker isolation, Tradex broker isolation).
- New contract added: **"Runtime broker-implementation isolation"** — `source_modules =
  ["runtime"]`, `forbidden_modules = ["brokers.providers.dhan", "brokers.providers.upstox", "brokers.providers.paper",
  "brokers.common"]`. This closes the last unenforced direction from the ADR.
- Tracked exceptions (the current `runtime/` violations, removed in Phase 5 / G1 / P5-3):
  - `runtime.broker_infrastructure -> brokers.providers.dhan.config.capabilities`
  - `runtime.broker_infrastructure -> brokers.providers.upstox.capabilities`
  - `runtime.broker_accessors -> brokers.providers.paper`
  - `runtime.broker_accessors -> brokers.providers.dhan.**`
  - `runtime.broker_accessors -> brokers.providers.upstox.**`
- A `layers`-type "Layered dependency spine" contract was attempted and **rejected**: it
  broke because `application -> domain` and `infrastructure -> domain` edges are correct
  (lower layers depend on `domain` ports). The inward-only spine is therefore enforced via
  the `forbidden`-style contracts above, not a `layers` contract. Documented here to avoid
  re-attempting it.
- Backlog cross-reference: **G1** (runtime concrete-broker coupling) is the consumer of the
  tracked exceptions; closing G1 deletes those `ignore_imports` lines.
- Verification: `PYTHONPATH="$(pwd)/src" venv/bin/lint-imports --config pyproject.toml`
  → all 16 contracts KEPT.
