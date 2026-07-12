# D0.5 — Technical Debt Register

> **Generated:** 2026-07-12 | **Scope:** Full `src/` tree | **Method:** Static analysis + file LOC counts + grep pattern matching

All line counts verified via `wc -l`. Severity reflects both maintenance burden and risk of leaving unaddressed.

---

## High Priority — Fix in Phase 5

| ID | Description | File(s) | LOC | Effort | Phase |
|----|-------------|---------|-----|--------|-------|
| **TD-H01** | **God class: TradingContext** — 809 LOC dataclass holding session state, gateway refs, quotas, and routing. Violates SRP; every new OMS feature adds another field here. | `src/application/oms/context.py` | 809 | L (2-3 days) | 5 |
| **TD-H02** | **God class: TradingOrchestrator** — 807 LOC orchestrating strategy execution, feature fetching (with `ThreadPoolExecutor`), risk gates, and order dispatch. | `src/application/trading/trading_orchestrator.py` | 807 | L (2-3 days) | 5 |
| **TD-H03** | **God class: ReplayEngine** — 1125 LOC bar-by-bar replay engine mixing pipeline execution, order routing, position tracking, and result accumulation. Largest single file. | `src/analytics/replay/engine.py` | 1125 | XL (3-5 days) | 5 |
| **TD-H04** | **God class: RiskManager** — 678 LOC deterministic risk checks with kill-switch state, daily PnL tracking, circuit breakers, and order-level pre-trade gates. | `src/application/oms/_internal/risk_manager.py` | 678 | L (2-3 days) | 5 |
| **TD-H05** | **God class: DhanExtendedCapabilities** — 366 LOC Dhan-specific extended order operations (super/forever/trigger/GTT/cover/slice/exit-all) in a single class. | `src/brokers/dhan/extended.py` | 366 | M (1-2 days) | 5 |
| **TD-H06** | **Event types monolith** — 1008 LOC single file containing all domain event dataclasses. Any event addition requires editing this file; merge conflicts inevitable. | `src/domain/events/types.py` | 1008 | L (2-3 days) | 5 |
| **TD-H07** | **Capability catalog monolith** — 905 LOC file defining all broker capabilities, rate-limit profiles, and feature flags in one place. | `src/domain/capability_manifest/catalog.py` | 905 | L (2-3 days) | 5 |
| **TD-H08** | **Universe monolith** — 808 LOC file managing instrument universe, session state, market hours, and symbol resolution. | `src/domain/universe.py` | 808 | L (2-3 days) | 5 |
| **TD-H09** | **Instrument monolith** — 819 LOC Instrument class mixing identity, pricing, quoting, provider delegation, and historical fetch. Dual-port collision with deprecated aggregate warning. | `src/domain/instruments/instrument.py` | 819 | L (2-3 days) | 5 |
| **TD-H10** | **Legacy dead code: top-level `brokers/dhan/`** — Old `gateway.py` (536 LOC) and `orders.py` (801 LOC) under top-level `brokers/dhan/` coexist with the canonical `src/brokers/dhan/` package. 1337 LOC of stale, shadowing code. | `brokers/dhan/gateway.py`, `brokers/dhan/orders.py` | 1337 | S (0.5 days) | 5 |
| **TD-H11** | **`PYTEST_CURRENT_TEST` in production code** — 5 production files branch on pytest env-var: `OmsOrderCommand.__post_init__`, `SqliteOrderStore.__init__`, `_auth_none_allowed`, `assert_runtime_parity_or_raise`, `is_production_environment`. Couples production logic to test runner internals. | `src/application/oms/order_manager.py:87-95`, `src/infrastructure/persistence/sqlite_order_store.py:94`, `src/interface/api/auth.py:33`, `src/runtime/parity_gate.py:17`, `src/runtime/production_config.py:19` | ~30 diff lines | M (1 day) | 5 |
| **TD-H12** | **`__import__("logging")` anti-pattern** — Production code uses `__import__("logging").getLogger(...)` instead of top-level imports. Found in `order_validator.py`, `trade_recorder.py`, and `brokers/dhan/api/async_http_client.py` (which also uses `__import__("time")`). Hides dependencies, defeats static analysis. | `src/application/oms/order_validator.py:24`, `src/application/oms/trade_recorder.py:22`, `src/brokers/dhan/api/async_http_client.py:196,337,381` | ~10 usages | S (0.5 days) | 5 |
| **TD-H13** | **Empty `market_data/` directory** — Both `market_data/` (root-level) and `src/market_data/` exist. `src/market_data/` contains only `__init__.py` + `market_surface.py` (conventions package). The root-level `market_data/` holds runtime artefacts (SQLite, DuckDB, JSON) that should not be in the repo. | `market_data/`, `src/market_data/` | 2 dirs | S (0.5 days) | 5 |

---

## Medium Priority — Fix in Phase 3-4

| ID | Description | File(s) | LOC | Effort | Phase |
|----|-------------|---------|-----|--------|-------|
| **TD-M01** | **Scattered backward-compat re-exports** — `tradex.runtime.__init__.py` contains a 100+ entry `FACADE_TO_CANONICAL` deprecation shim. Additional re-exports in `brokers/exceptions/__init__.py`, `brokers/events/__init__.py`, `infrastructure/resilience/errors.py`, `infrastructure/lifecycle/lifecycle.py`, `datalake/core/duckdb_utils.py`, `application/execution/simulated_fill.py`, `analytics/replay/models.py`. At least 8 files with `# noqa: F401` re-exports. | `src/tradex/runtime/__init__.py` (120+ entries), plus 7 other files | ~200 shim LOC + 120 LOC facade loader | M (1-2 days) | 3-4 |
| **TD-M02** | **Duplicate FakeBrokerGateway** — Two independent implementations: `tests/fixtures/fake_broker_gateway.py` (OrderTransportPort fake) and `tests/fakes/fake_oms.py:FakeBrokerGateway` (IBrokerGateway fake). Different interfaces, different test ergonomics, confusing for contributors. | `tests/fixtures/fake_broker_gateway.py`, `tests/fakes/fake_oms.py` | ~180 LOC total (2 copies) | S (0.5 days) | 3-4 |
| **TD-M03** | **Hardcoded broker-specific remediation strings in CLI shell** — `_shell_nav.py` has `if broker_id == "dhan"` / `if broker_id == "upstox"` branches with broker-specific error remediation text (DHAN_ACCESS_TOKEN, UPSTOX_ACCESS_TOKEN, TOTP timing, Upstox maintenance windows). Adding a broker requires editing this file. | `src/brokers/cli/_shell_nav.py:350-390` | ~40 branching LOC | S (0.5 days) | 3-4 |
| **TD-M04** | **Dual broker registration** — Brokers are registered via both `pyproject.toml` entry points (`tradex.brokers` group) AND `ensure_core_plugins()` fallback in `infrastructure/broker_plugin.py` with duplicated metadata. `session.py` calls `ensure_core_plugins()` before every `get_broker_plugin()`. Drift-prone; metadata lives in two places. | `pyproject.toml` (entry-points), `src/infrastructure/broker_plugin.py:50-60`, `src/tradex/session.py:82-97` | ~118 LOC plugin infra + scattered call sites | M (1 day) | 3-4 |

---

## Low Priority — Fix in Phase 7-8

| ID | Description | File(s) | LOC | Effort | Phase |
|----|-------------|---------|-----|--------|-------|
| **TD-L01** | **`cache_redis.py` ThreadPoolExecutor created per call** — `_run_sync()` spins up a new `concurrent.futures.ThreadPoolExecutor(max_workers=1)` on every synchronous cache operation (get/set/delete/has). Should be a class-level pool or module singleton. | `src/infrastructure/cache_redis.py:89-93` | 5 LOC per call | S (0.5 days) | 7-8 |
| **TD-L02** | **SecretManager singleton with class-level state** — Uses classic `_instance` / `_instance_lock` class variables as singleton pattern. Hard to test (requires `reset_instance()`), hides dependency graph, prevents scoped instances for multi-account scenarios. | `src/infrastructure/security/secret_manager.py:55-58,161-182` | 429 total file | S (0.5 days) | 7-8 |
| **TD-L03** | **`session_infra.py` module-level global** — `_shared_quota` is a module-level mutable global mutated via `global _shared_quota` inside `wire_gateway_for_session()`. Multi-session or test isolation requires careful teardown. | `src/runtime/session_infra.py:12,33` | 90 total file | S (0.5 days) | 7-8 |

---

## Summary Statistics

| Priority | Count | Total LOC Impact | Target Phase |
|----------|-------|------------------|--------------|
| High | 13 | ~7,033 | Phase 5 |
| Medium | 4 | ~438+ (diffuse) | Phase 3-4 |
| Low | 3 | ~112 (behavioral) | Phase 7-8 |
| **Total** | **20** | **~7,583+** | — |

### Notes

- **TD-H10** (1337 LOC legacy dead code in `brokers/dhan/`) is the quickest win — delete the directory if no imports reference it.
- **TD-H11** + **TD-H12** are anti-pattern violations already documented in `TRANSFORMATION_ROADMAP.md` D5.5; this register formalizes them as tracked debt.
- **TD-M01** (facade shim) is the largest backward-compat surface; the `tradex.runtime` deprecation loader alone maps 80+ module paths.
- The `__import__` anti-pattern appears in **10+ production and test files** beyond the 2 mentioned in the roadmap (scripts, tests, and broker code also use it).
- **TD-M04** dual registration is self-documented in `pyproject.toml` comments acknowledging the duplication was intentional as a fallback — but the drift risk is real.
