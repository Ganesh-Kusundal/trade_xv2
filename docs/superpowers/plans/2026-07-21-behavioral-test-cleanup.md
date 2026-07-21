# Behavioral Test Suite Cleanup — Implementation Plan

> **For agentic workers:** Execute phase-by-phase; each phase is a reviewable unit. Do not skip preserve list checks.

**Goal:** Runtime tests verify business behavior; structural rules live in static analysis.

**Architecture:** Phase 0 ledger → Phase 1 static migration → Phases 2–5 pyramid rewrites.

**Tech Stack:** pytest, import-linter, ruff, `scripts/ci/`

## Global Constraints

- No mock data in production code
- Preserve list in `docs/superpowers/ledgers/test-preserve-list.md`
- Update `tests/README.md` and `context/progress-tracker.md` after each phase
- Run `graphify update .` after structural moves

---

## Phase 0 — Ledger ✓

- [x] `scripts/ci/classify_test_suite.py`
- [x] `docs/superpowers/ledgers/test-disposition-phase0.md`
- [x] Design spec + preserve list

---

## Phase 1 — Architecture static gates

### 1a. import-linter contracts

- [ ] Add `datalake` ↛ `analytics`
- [ ] Add `application` ↛ `tradex`
- [ ] Add `interface.api` ↛ `interface.ui`

### 1b. CI scripts (`scripts/ci/`)

- [ ] `check_file_size_limit.py` (from test_file_size_limit)
- [ ] `check_no_mock_in_integration.py`
- [ ] `check_broker_name_branching.py`

### 1c. Delete MOVE_STATIC architecture duplicates

- [ ] Remove pytest files listed in classify script ARCH_MOVE_STATIC set

### 1d. Rewrite capital-path tests

- [ ] `test_order_placement_spine.py`
- [ ] `test_fail_closed_capital_paths.py`
- [ ] `test_stream_oms_lock_discipline.py`
- [ ] `test_execution_target_resolver.py`

### Verify

- [ ] `PYTHONPATH=src lint-imports --config pyproject.toml`
- [ ] `pytest tests/architecture -q`

---

## Phase 2 — Unit domain

- [ ] Remove AST from unit/security, unit/datalake source scans → CI
- [ ] Rewrite `test_identity_coercion.py` to real domain objects

---

## Phase 3 — Unit brokers

- [ ] Split AST blocks from `test_gateway_error_surface_contracts.py`
- [ ] Rewrite `test_capabilities_validator_fields.py` via public API
- [ ] Golden bus: replace MagicMock with in-memory collector in dhan/upstox bus golden tests

---

## Phase 4 — Component / UI

- [ ] Move `tests/component/ui/test_risk_controls.py`, `test_order_placement.py`, doctor suites → `tests/unit/interface/ui/`

---

## Phase 5 — Integration / e2e

- [ ] Move `integration/capability/test_cli_gateway_calls.py` → architecture/CI
- [ ] Move `integration/brokers/dhan/regression/test_recent_fixes.py` → unit
- [ ] Rewrite `test_risk_deny_never_hits_venue.py` with recording fake (no MagicMock PM)

---

## Verification (full)

```bash
python3 scripts/ci/classify_test_suite.py
PYTHONPATH=src lint-imports --config pyproject.toml
PYTHONPATH=src pytest tests/architecture tests/unit/domain -q
PYTHONPATH=src pytest tests/unit/brokers/common/test_acl.py tests/unit/brokers/common/test_wire_base.py -q
```
