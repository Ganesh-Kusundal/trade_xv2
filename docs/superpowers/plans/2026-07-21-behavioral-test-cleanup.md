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

- [x] `check_file_size_limit.py` (from test_file_size_limit)
- [x] `check_no_mock_in_integration.py`
- [x] `check_broker_name_branching.py`
- [x] Wired into `.github/workflows/ci.yml` + `architecture-enforcement.yml`

### 1c. Delete MOVE_STATIC architecture duplicates

- [x] Removed pytest wrappers covered by CI: file_size, no_mock, broker_name_branching, canonical_domain_imports, datalake_no_analytics, analytics_simulation_isolation, cli_gateway_calls, rest_data_source_contract
- [ ] Remaining MOVE_STATIC without CI twin (follow-up)

### 1d. Rewrite capital-path tests

- [ ] `test_order_placement_spine.py`
- [ ] `test_fail_closed_capital_paths.py`
- [ ] `test_stream_oms_lock_discipline.py`
- [ ] `test_execution_target_resolver.py`

### Hierarchy cleanup (Pass A–D) ✓

- [x] Delete temporary duplicate component/ui + integration recent_fixes copies
- [x] Move MOVE_LAYER UI/doctor tests → `tests/unit/interface/ui/`
- [x] Capability manifest contract → `tests/architecture/`; slim future_chain integration
- [x] Rename process vocabulary; expand behavioral-name forbidden list

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

- [x] Move mock CLI/doctor suites → `tests/unit/interface/ui/` (Pass B)

---

## Phase 5 — Integration / e2e

- [x] Move `integration/capability/test_cli_gateway_calls.py` → CI script
- [x] Move `integration/brokers/dhan/regression/test_recent_fixes.py` → unit (renamed behavioral)
- [ ] Rewrite `test_risk_deny_never_hits_venue.py` with recording fake (no MagicMock PM)

---

## Verification (full)

```bash
python3 scripts/ci/classify_test_suite.py
PYTHONPATH=src lint-imports --config pyproject.toml
PYTHONPATH=src pytest tests/architecture tests/unit/domain -q
PYTHONPATH=src pytest tests/unit/brokers/common/test_acl.py tests/unit/brokers/common/test_wire_base.py -q
```
