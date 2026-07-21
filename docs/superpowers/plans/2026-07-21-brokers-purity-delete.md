# Plan: Brokers purity delete (CLI / cert / diagnostics)

> **For agentic workers:** COMPLETE ALL ITEMS. Design: `docs/superpowers/specs/2026-07-21-brokers-purity-delete-design.md`

**Goal:** Delete impure packages from `src/brokers`; keep adapters pure.

### Task 1: Market-hours carve-out
- Add `is_nse_market_open` to `src/plugins/exchanges/nse/calendar.py`
- Point `paper_orders` at it
- One tiny assert self-check or rely on existing paper tests

### Task 2: Delete packages + ops facades
- rm `cli/`, `certification/`, `diagnostics/`
- rm `platform_ops.py`, `services/platform_ops.py`, `services/operations.py`
- Strip exports from `services/__init__.py`, `services/core.py`

### Task 3: Downstream
- Relocate `PreferencesStore` → `tradex/preferences.py`
- Strip `tradex broker` + brokers.cli imports from `tradex/cli.py`
- Remove doctor/verify/benchmark/certify from `platform_bridge` + `broker_ops`
- UI doctor: drop `_services_doctor_results` / `run_doctor` bridge; keep UI-native checks
- Remove or unregister UI `certify` / `benchmark` if they only wrap deleted ops
- Drop `broker` script + import-linter ignores in `pyproject.toml`

### Task 4: Tests / scripts
- Delete tests under `tests/**/cli`, `certification`, `diagnostics` for brokers
- Delete/update arch tests: `test_cert_*`, `test_platform_ops_unity`
- Fix `broker_selftest`, MCP, scripts that import deleted modules

### Task 5: Sync
- `graphify update src`
- Update `context/progress-tracker.md`
