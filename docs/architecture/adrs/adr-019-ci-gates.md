# ADR-019: CI Gate Semantics

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Integration/Release lane, Chief Architect

## Context

CI workflows mixed **blocking** checks (must pass to merge) with **advisory**
steps (`continue-on-error: true`) that silently swallowed safety failures.
Operators could not tell whether green meant "safe to deploy" or "paths exist
but doctor failed."

Phase 3 repaired stale script paths; this ADR defines the semantics so new
workflows do not reintroduce false confidence.

## Decision

### Gate tiers

| Tier | Meaning | CI behavior |
|------|---------|-------------|
| **blocking** | Merge/deploy gate | Job fails → PR blocked |
| **advisory** | Signal only | May use `continue-on-error`; must be labeled |
| **blocked** | Requires secrets/credentials | Skipped with explicit reason in summary |

### Blocking gates (mandatory on `main` PRs)

- `lint-imports` — 15/15 contracts (see `DEPENDENCY_RULES.md`)
- `ruff check` + `ruff format --check`
- `pytest` pyramid: `tests/unit`, `tests/component`, `tests/architecture`
- `tests/architecture/test_workflow_paths.py` — no stale CI paths
- `tests/architecture/test_domain_no_broker_imports.py`
- `tests/architecture/test_application_no_infra_imports.py`
- Coverage ≥ 80% (`fail_under` in `pyproject.toml`)
- `bandit` HIGH severity
- Paper broker `certify` matrix (when wired in `production_gate.yml`)

### Advisory gates (until Phase 4 exit)

- `broker doctor` on live brokers (flaky network; nightly instead)
- Mutation testing (nightly workflow)
- `mypy` / `safety` (warn until Phase 7 hardening)

Advisory jobs MUST include `advisory` in the job name or workflow filename
suffix (e.g. `mutation_nightly.yml`).

### Forbidden patterns

1. `continue-on-error: true` on **blocking** gates without an open TRANS task
   and expiry date in workflow comment.
2. Referencing `scripts/verify/*` in CI without a matching
   `test_workflow_paths.py` entry (use `broker verify` / pytest instead).
3. `SKIP_PARITY_GATE` in production workflows.

### Result vocabulary

Certification and doctor commands emit:

- `passed` — check succeeded
- `failed` — check ran and found defects
- `blocked` — prerequisites missing (secrets, market hours, broker down)

CI summaries must surface `blocked` distinctly from `failed`.

## Consequences

- `production_gate.yml` removes silent `continue-on-error` on safety steps
  as TRANS-P3-004 completes.
- New architecture tests enforce import direction without duplicating every
  import-linter ignore (approved debt list in test + pyproject.toml).
- Nightly workflows own flaky/live checks; PR CI stays deterministic.

## Compliance

- TRANS-P3-004, TRANS-P3-012
- `docs/engineering/STANDARDS.md` § CI
- `TESTING-STRATEGY.md` § CI quality gates