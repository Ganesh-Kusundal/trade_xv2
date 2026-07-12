# D0.6 — Test Coverage Map

> Generated from live file system scan of `/Users/apple/Downloads/Trade_XV2`

---

## 1. Test File Counts by Directory

| Directory | `test_*.py` files | Purpose |
|---|---:|---|
| `tests/unit/` | **424** | Domain / pure business-rule tests |
| `tests/component/` | **151** | Single-service tests (OMS, execution, registry) |
| `tests/integration/` | **95** | Tests that call external broker APIs |
| `tests/architecture/` | **55** | Architecture / boundary / import-linter guard tests |
| `tests/e2e/` | **33** | End-to-end trading flow tests |
| `tests/chaos/` | **13** | Chaos / concurrency stress recovery tests |
| **Total** | **771** | |

### In-tree tests (inside `src/`)

| Path | Count |
|---|---:|
| `src/interface/ui/commands/load_test.py` | 1 (not a test file — load-testing runner) |

No `test_*.py` files exist inside `src/` — all tests live under `tests/`.

---

## 2. Source Module → Test File Mapping

### `src/brokers/` (164 source files)

| Source Module | Has Unit Tests? | Has Component Tests? | Has Integration Tests? |
|---|---|---|---|
| `session/broker_session.py` | ❌ | ❌ | ❌ |
| `cli/broker.py` | ✅ `test_cli_shell.py`, `test_shell_nav.py`, `test_shell_ui.py`, `test_cli_render.py` | ✅ `test_commands.py` | ❌ |
| `mcp/tools.py` | ❌ | ❌ | ❌ |
| `mcp/server.py` | ❌ | ❌ | ❌ |
| `paper/paper_gateway.py` | ✅ `test_paper.py` | ❌ | ❌ |
| `paper/paper_orders.py` | ✅ `test_paper_orders_concurrency.py` | ❌ | ✅ `test_e2e_paper_trading_os.py` |
| `paper/data_provider.py` | ✅ `test_data_provider_history.py` | ❌ | ❌ |
| `paper/contract/` | ✅ `test_paper_market_coverage.py`, `test_paper_contract.py` | ❌ | ✅ `test_market_coverage.py` (dhan, upstox) |
| `dhan/domain.py` | ❌ | ❌ | ❌ |
| `dhan/data/` | ❌ | ❌ | ✅ (15+ integration tests) |
| `dhan/execution/` | ❌ | ❌ | ✅ `test_live_order_lifecycle.py` etc. |
| `dhan/streaming/` | ❌ | ❌ | ✅ `test_live_streaming.py`, `test_live_websocket.py` |
| `dhan/websocket/` | ❌ | ❌ | ✅ `test_ws_parity.py` etc. |
| `dhan/auth/` | ❌ | ❌ | ✅ (via `auth_integration` marker) |
| `dhan/instruments/` | ❌ | ❌ | ✅ `test_live_instruments.py` |
| `dhan/portfolio/` | ❌ | ❌ | ✅ `test_live_portfolio.py` |
| `upstox/broker.py` | ✅ (18+ tests) | ❌ | ✅ (12+ integration tests) |
| `upstox/auth/` | ✅ `test_login.py`, `test_token_manager.py`, etc. | ❌ | ❌ |
| `upstox/adapters/` | ✅ `test_adapters_tick_translator.py` etc. | ❌ | ✅ `test_live_*` suite |
| `upstox/market_data/` | ❌ | ❌ | ✅ (10+ integration tests) |
| `upstox/orders/` | ✅ `test_order_command_adapter.py`, `test_order_query_adapter.py` | ❌ | ✅ `test_live_order_lifecycle.py` |
| `upstox/websocket/` | ✅ `test_websocket_*` (6 tests) | ❌ | ✅ `test_ws_parity.py` |
| `common/` | ✅ (20+ tests) | ❌ | ❌ |
| `diagnostics/` | ❌ | ❌ | ❌ |
| `runtime/` | ❌ | ✅ `test_trading_runtime_factory.py`, `test_broker_discovery.py` | ❌ |
| `extensions/` | ❌ | ❌ | ❌ |
| `services/core.py` | ❌ | ❌ | ❌ |
| `certification/` | ❌ | ❌ | ✅ `test_cert_schema_v2.py`, `test_cert_path_unity.py` |

### `src/application/` (70 source files)

| Source Module | Has Tests? |
|---|---|
| `oms/order_manager.py` | ✅ `test_order_manager_core_behavior.py` |
| `oms/risk_manager.py` | ✅ `test_risk_manager_margin.py`, `test_risk_manager_concurrency.py`, etc. |
| `oms/position_manager.py` | ✅ `test_order_position_updater.py` |
| `oms/composition.py` | ✅ `test_composition.py`, `test_process_oms_book_is_shared.py` |
| `oms/reconciliation/` | ✅ `test_reconciliation_service.py`, `test_reconciliation_gate.py` |
| `oms/square_off_service.py` | ❌ (no direct test) |
| `oms/extended_order_service.py` | ✅ `test_extended_order_service_registry.py`, `test_extended_order_risk.py` |
| `oms/daily_pnl_reset_scheduler.py` | ❌ |
| `execution/execution_service.py` | ✅ `test_execution_service.py` |
| `execution/gateway_submit.py` | ✅ `test_gateway_submit.py` |
| `execution/place_order_use_case.py` | ✅ `test_order_placement.py` (component) |
| `execution/cancel_order_use_case.py` | ❌ (no direct test) |
| `streaming/orchestrator.py` | ❌ (no direct test) |
| `streaming/session_manager.py` | ❌ (no direct test) |
| `trading/trading_orchestrator.py` | ✅ `test_trading_orchestrator_*.py` (4 tests) |
| `trading/multi_strategy_runtime.py` | ✅ `test_multi_strategy_runtime.py` |
| `portfolio/portfolio_service.py` | ✅ `test_portfolio_service.py` |
| `strategy_engine/engine.py` | ❌ (no direct test) |
| `composer/` | ✅ `test_execution_composer.py` |
| `data/historical_coordinator.py` | ❌ (tested indirectly via integration) |
| `audit.py` | ❌ (no direct test) |
| `services/api_readiness.py` | ✅ (via `test_production_readiness_fail_closed.py`) |
| `services/download_engine.py` | ✅ `test_download_engine_persists_history.py` |
| `services/instrument_registry.py` | ✅ `test_instrument_registry_lookup.py` |
| `services/production_readiness.py` | ✅ `test_production_readiness_fail_closed.py` |

### `src/analytics/` (80 source files)

| Source Module | Has Tests? |
|---|---|
| `backtest/engine.py` | ✅ (via e2e `test_backtest_session_history.py`) |
| `backtest/fast_backtest.py` | ❌ |
| `scanner/` | ✅ `test_scanner_runner_emits_candidates.py` |
| `scanner/rules/` | ❌ (no direct test) |
| `pipeline/pipeline.py` | ✅ (indirectly via backtest/strategy tests) |
| `strategy/builtins/halftrend.py` | ❌ |
| `strategy/registry.py` | ❌ |
| `indicators/halftrend.py` | ❌ (no direct unit test) |
| `indicators/market_structure.py` | ❌ |
| `ranking/ranking.py` | ❌ |
| `market_breadth/breadth.py` | ❌ |
| `sector/` | ❌ |
| `views/` | ❌ (tested via API endpoint tests) |
| `replay/` | ✅ (via `test_replay_orchestrator_advances_bars.py`, `test_replay_backtest_flow.py`) |
| `volatility/` | ❌ |
| `volume_profile/` | ❌ |

### `src/infrastructure/` (120+ source files)

| Source Module | Has Tests? |
|---|---|
| `event_bus/event_bus.py` | ✅ (via chaos `test_event_bus_replay_api.py`, component tests) |
| `resilience/circuit_breaker.py` | ✅ (via `test_circuit_breaker_recovery_flow.py`) |
| `resilience/rate_limiter.py` | ✅ (via `test_rate_limit_exhaustion.py`) |
| `resilience/retry.py` | ❌ |
| `persistence/sqlite_order_store.py` | ✅ `test_sqlite_order_store_restart.py` |
| `persistence/sqlite_execution_ledger.py` | ❌ |
| `idempotency/` | ❌ (tested indirectly via OMS) |
| `config/settings.py` | ❌ |
| `cache.py` | ❌ |
| `bootstrap.py` | ❌ |
| `di.py` | ❌ |
| `health.py` | ✅ (via health endpoint tests) |
| `metrics/prometheus.py` | ✅ (via e2e `test_metrics.py`) |
| `security/` | ❌ (no direct test) |
| `lifecycle/` | ✅ (via `test_graceful_shutdown.py`) |
| `observability/` | ✅ (via `test_structured_logging.py`, `test_tracing.py`) |
| `time/clock.py` | ❌ |
| `db/duckdb_pool.py` | ✅ (via `test_connection_pool_limits_concurrency.py`) |
| `providers/` | ❌ |

### `src/domain/` (160+ source files)

| Source Module | Has Tests? |
|---|---|
| `instruments/instrument.py` | ✅ (via architecture `test_domain_bar_types.py`, `test_domain_market_types.py`) |
| `options/option_chain.py` | ❌ (tested via integration) |
| `options/greeks.py` | ✅ (via `test_derivatives_greeks.py`) |
| `orders/` | ✅ (via `test_order_placement_spine.py`, OMS tests) |
| `entities/` | ✅ (via domain tests) |
| `value_objects/` | ✅ `test_domain_value_object_purity.py` |
| `ports/` | ✅ (via `test_domain_ports_forbid_tradex_imports.py`) |
| `extensions/` | ❌ |
| `risk/` | ❌ |
| `portfolio/` | ❌ |
| `state_machine.py` | ❌ |
| `events/` | ❌ (tested via event bus tests) |
| `primitives/` | ❌ |
| `connect_errors.py` | ❌ |
| `errors.py` | ❌ (via `test_no_duplicate_error_hierarchies.py`) |

---

## 3. Critical Paths LACKING Test Coverage

### 🔴 High Priority — No tests at all

| Module | Path | Risk |
|---|---|---|
| **BrokerSession** | `src/brokers/session/broker_session.py` | Primary SDK entry point — untested |
| **MCP Tools** | `src/brokers/mcp/tools.py` | 24 MCP tools for LLM consumption — untested |
| **MCP Server** | `src/brokers/mcp/server.py` | Server lifecycle — untested |
| **Agent Tools** | `src/interface/agent/tools.py` | AI agent surface — 12 tools untested |
| **Agent Guardrails** | `src/interface/agent/guardrails.py` | Rate limiting / symbol allowlists — untested |

### 🟡 Medium Priority — Partially tested

| Module | Gap |
|---|---|
| `src/application/oms/square_off_service.py` | Square-off workflow (high risk) — no test |
| `src/application/oms/daily_pnl_reset_scheduler.py` | PnL reset (critical scheduling) — no test |
| `src/application/execution/cancel_order_use_case.py` | Cancel flow — no direct test |
| `src/application/streaming/orchestrator.py` | Streaming orchestration — no test |
| `src/application/strategy_engine/engine.py` | Strategy engine core — no test |
| `src/analytics/scanner/rules/` | Scanner rule compiler + engine — no test |
| `src/analytics/ranking/ranking.py` | Ranking engine — no test |
| `src/analytics/market_breadth/breadth.py` | Market breadth — no test |
| `src/analytics/sector/` | Sector analytics (5 files) — no test |
| `src/infrastructure/persistence/sqlite_execution_ledger.py` | Execution ledger persistence — no test |
| `src/infrastructure/security/` | Security module (3 files) — no test |
| `src/infrastructure/cache.py` | Caching layer — no test |
| `src/infrastructure/config/settings.py` | Settings management — no test |
| `src/domain/state_machine.py` | State machine core — no test |
| `src/domain/extensions/` | Extension framework (12 files) — no test |

### 🟢 Architecture layer well-covered

Architecture tests (55 files) provide strong boundary enforcement:
- Import direction and layering
- Domain isolation (no broker, no pandas, no tradex imports)
- Wire boundary enforcement
- Cross-cutting concerns
- Flow contracts
- Public SDK surface invariants

---

## 4. Test Categories and Markers

### Defined in `pyproject.toml` → `[tool.pytest.ini_options]`

| Marker | Description | Category |
|---|---|---|
| `unit` | Domain / pure business-rule tests | Unit |
| `component` | Single-service tests (OMS, execution, registry) | Component |
| `architecture` | Architecture / boundary / import-linter guard tests | Architecture |
| `golden` | Golden dataset / replay parity fixtures | Integration |
| `chaos` | Chaos / concurrency stress recovery tests | Chaos |
| `contract` | Broker/module contract tests | Integration |
| `dhan` | DhanHQ integration tests | Integration |
| `integration` | Tests that call external broker APIs | Integration |
| `sandbox` | Sandbox tests that may place and cancel orders | Integration |
| `live_readonly` | Live tests that must only read from real endpoints | Integration |
| `performance` | Latency and throughput benchmarks | E2E |
| `upstox` | Upstox-specific unit tests | Unit |
| `upstox_integration` | Upstox integration tests (gated by `UPSTOX_INTEGRATION=1`) | Integration |
| `upstox_sandbox` | Sandbox tests for Upstox | Integration |
| `upstox_live_readonly` | Live read-only tests for Upstox | Integration |
| `upstox_sdk_compat` | SDK compatibility tests | Unit |
| `stress` | Long-running concurrency stress tests | Chaos |
| `pre_prod` | Tests required on pre-prod gate (`PRE_PROD_GATE=1`) | Integration |
| `regression` | Part of Dhan regression suite | Integration |
| `off_market_safe` | Live-readonly REST tests; safe outside NSE hours | Integration |
| `market_hours` | WebSocket/streaming tests; require NSE 09:15-15:30 IST | Integration |
| `auth_integration` | Live TOTP bootstrap and WebSocket reconnect | Integration |
| `cli_endpoint` | Offline subprocess smoke for CLI endpoints | Component |
| `cli_endpoint_live` | Live-readonly subprocess smoke | Integration |
| `cli_endpoint_sandbox` | Sandbox order placement via CLI | Integration |
| `paper_replay_parity` | Paper trading ↔ Replay engine parity | Integration |
| `cross_broker_parity` | Cross-broker data source parity | Integration |
| `certification` | Broker certification and CLI smoke tests | Integration |
| `live_backtest_parity` | Live ↔ Backtest execution parity | Integration |
| `scanner_determinism` | Scanner output determinism | Component |
| `feature_parity` | Feature computation parity across runs | Component |
| `oms_integration` | OMS and broker gateway integration tests | Integration |
| `memory` | Memory profiling and leak detection tests | Chaos |
| `e2e` | End-to-end trading flow tests | E2E |
| `slow` | Tests that take >1 second to execute | All |
| `live_orders` | Guarded real order placement (`TRADEX_LIVE_ORDERS=1`) | Integration |
| `property` | Property-based tests (hypothesis) | Unit |
| `mutation` | Mutation testing (tests verify behavior) | All |

### Fixtures in `tests/conftest.py`

| Fixture | Scope | Description |
|---|---|---|
| `_register_domain_runtime_hooks` | session, autouse | Wires broker factories into domain hooks |
| `market_is_open` | function | Skips test if market is closed |
| `live_credentials` | function | Provides Dhan `(client_id, access_token)` or skips |
| `upstox_credentials` | function | Provides Upstox `(api_key, access_token)` or skips |
| `build_test_trading_context` | function | Helper to build TradingContext with event defaults |

### Sub-conftest files

| Path | Purpose |
|---|---|
| `tests/unit/brokers/paper/conftest.py` | Paper broker test fixtures |
| `tests/unit/brokers/common/conftest.py` | Common broker test fixtures |
| `tests/unit/brokers/dhan/conftest.py` | Dhan unit test fixtures |
| `tests/integration/brokers/upstox/conftest.py` | Upstox integration fixtures |
| `tests/integration/brokers/dhan/conftest.py` | Dhan integration fixtures |
| `tests/integration/brokers/dhan/regression/conftest.py` | Dhan regression fixtures |
| `tests/integration/api/conftest.py` | API integration fixtures |
| `tests/component/ui/conftest.py` | UI component fixtures |

### Pytest configuration

```ini
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "-ra --strict-markers --tb=short --durations=10"
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```
