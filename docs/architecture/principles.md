# Architecture Principles — TradeXV2

**Version:** 1.0 · **Phase:** 1 (Transformation Roadmap) · **Date:** 2026-07-12

These 20 non-negotiable principles are derived from patterns that are already
actively enforced in the codebase. Each principle is grounded in concrete
test coverage or production code — not aspirational goals.

---

### P01: Domain Layer Isolation
**Statement:** The domain layer must never import from application, brokers, infrastructure, analytics, interface, config, datalake, plugins, tradex, or runtime layers.
**Rationale:** Domain logic is the heart of the system. If it depends on outer layers, changing infrastructure ripples into business rules, making the system brittle and untestable in isolation.
**Current Evidence:** `tests/architecture/test_domain_isolation.py` — AST-walks every `.py` file under `src/domain/` and asserts zero imports from 10 forbidden layer prefixes. Enforced per-layer via parametrized tests.
**Violation Example:** Adding `from infrastructure.event_bus import EventBus` inside `src/domain/orders/intent.py` to publish an event directly.

---

### P02: No Broker-Name Branching in Generic Code
**Statement:** The OMS, certification suite, and rate limiter must never branch on concrete broker name strings (e.g., `"dhan"`, `"upstox"`). Dispatch must be capability-driven.
**Rationale:** Adding a broker must require zero edits to generic infrastructure. Name-based branching creates N×M maintenance surface; capability metadata enables O(1) extensibility.
**Current Evidence:** `tests/architecture/test_no_broker_name_branching.py` — scans OMS source, cert suite, and rate limiter for literal broker name strings and `broker_id == "..."` comparisons; fails on any match.
**Violation Example:** Writing `if broker_id == "dhan":` inside `src/application/oms/` to handle Dhan-specific order routing.

---

### P03: Gateway Surface Freeze
**Statement:** Public method sets on broker gateways are frozen allowlists. New product features belong on ports, extensions, or Instrument — not as new methods on gateway facades.
**Rationale:** Fat gateway objects become unmaintainable catch-alls. Frozen surfaces force feature design through composable ports rather than monolithic interfaces.
**Current Evidence:** `tests/architecture/test_gateway_surface_freeze.py` — captures method sets for `DhanBrokerGateway`, `UpstoxBrokerGateway`, and `PaperGateway` in frozen allowlists; any new method fails CI.
**Violation Example:** Adding `def super_order(self, ...)` directly on `DhanBrokerGateway` instead of registering a `SuperOrderExtension` via the `ExtensionRegistry`.

---

### P04: Money Paths Fail Closed
**Statement:** All money-moving code paths must fail loudly on errors. Silent no-ops, swallowed exceptions, and missing event publishes are forbidden on order lifecycle paths.
**Rationale:** A silent failure on a money path means the system believes an order was handled when it was not — leading to phantom capital, unrecorded fills, or stuck orders.
**Current Evidence:** `tests/architecture/test_fail_closed_capital_paths.py` — asserts order lifecycle publishes events, event bus handler failures go to DLQ + metrics, and the EventBus exposes `as_managed_service`.
**Violation Example:** Wrapping a broker `place_order` call in a bare `except: pass` that swallows network errors, leaving the local book in sync with an order the broker never saw.

---

### P05: Single OMS Per Process
**Statement:** Exactly one `TradingContext` (the process-wide OMS) may be registered per process. Live brokers without a registered context are refused.
**Rationale:** Multiple OMS instances would split the order book, risk capital, and ledger — destroying the single source of truth for money-moving state.
**Current Evidence:** `src/application/oms/composition.py` — `register_process_oms()` stores a single process-wide context; `require_process_oms()` raises with operator guidance if none exists.
**Violation Example:** Creating a second `TradingContext()` inside a scheduler thread and placing orders through it, bypassing the canonical OMS registered at startup.

---

### P06: Record-Then-Submit for Order Durability
**Statement:** Every order intent must be persisted to the execution ledger before any broker I/O is attempted.
**Rationale:** If the process crashes between ledger write and broker submission, recovery can replay the intent. Without persistence first, the intent is lost.
**Current Evidence:** `src/application/oms/ledger_outbox.py` — `persist_intent_then_submit()` calls `ledger.record_intent(intent)` before invoking `submit_fn()`.
**Violation Example:** Calling `broker.place_order()` first and only writing to the ledger after a successful response — a crash between those two steps loses the order permanently.

---

### P07: Strategy Pipeline Parity
**Statement:** The same `FeaturePipeline` and `StrategyPipeline` must be used across scanner, backtest, replay, paper, and live modes — no mode-specific evaluation branches.
**Rationale:** Parity ensures that a strategy tested in backtest produces identical signals in live mode. Mode-specific branches invalidate backtest confidence.
**Current Evidence:** `src/application/strategy_engine/engine.py` — `LiveStrategyEngine` accepts an injected `pipeline` and evaluates candidates through the same `evaluate()` interface regardless of mode.
**Violation Example:** Writing a `def evaluate_live()` method with different indicator logic than `def evaluate_backtest()`, causing backtest signals to diverge from live behavior.

---

### P08: Single Service Core
**Statement:** One implementation of each broker service must serve SDK, CLI, and MCP surfaces. No surface-specific code paths in the core.
**Rationale:** Duplicating logic per surface multiplies bugs and divergence. A single core ensures consistency and reduces maintenance cost.
**Current Evidence:** `src/brokers/services/core.py` (referenced by `tests/architecture/test_platform_ops_unity.py` and `tests/architecture/test_mcp_platform_ops_parity.py`) — one implementation, multiple callers.
**Violation Example:** Implementing `list_capabilities()` separately for the CLI and the SDK, with divergent behavior when a broker is offline.

---

### P09: Protocol-Based Interfaces
**Statement:** Domain ports must use `typing.Protocol` (structural subtyping), not abstract base classes (ABCs). Interfaces are defined by behavior, not inheritance.
**Rationale:** Protocols enable duck-typing test doubles without coupling to a base class. They also allow legacy code to satisfy interfaces without refactoring inheritance hierarchies.
**Current Evidence:** `src/domain/ports/protocols.py` — `DataProvider`, `ExecutionProvider`, `SubscriptionHandle`, and `MarginProviderPort` are all `@runtime_checkable Protocol` classes.
**Violation Example:** Defining `class MarketDataProvider(ABC)` in `domain/ports/` and requiring all data providers to `class BrokerDataProvider(MarketDataProvider)`, creating tight coupling.

---

### P10: Copy-On-Publish Events
**Statement:** Domain events must be published as immutable snapshots. Publishing must copy the event payload; subscribers must never mutate shared event state.
**Rationale:** Event consumers may process events asynchronously. Mutation by one subscriber corrupts the event for all others, causing non-deterministic bugs that are extremely hard to reproduce.
**Current Evidence:** `src/infrastructure/event_bus/event_bus.py` — `_prepare_event()` creates a copy of the event payload (via `dataclasses.replace` or dict copy) before dispatch.
**Violation Example:** Publishing a mutable `dict` as an event payload and having a subscriber pop keys from it, silently breaking downstream subscribers.

---

### P11: Dead Letter Queue Never Swallows Failures
**Statement:** Event handler failures must be routed to a DLQ with metrics. The system must never silently drop events.
**Rationale:** A dropped event on a money path means an unrecorded fill, a stale position, or a missed risk check. DLQ routing preserves observability while keeping the main path healthy.
**Current Evidence:** `src/infrastructure/event_bus/event_bus.py` — `_handle_handler_failure()` writes to `DeadLetterQueue` and records failure metrics. `tests/architecture/test_fail_closed_capital_paths.py` asserts `DeadLetterQueue` appears in the event bus source.
**Violation Example:** Wrapping event handler invocations in `try/except Exception: pass` to "keep the bus running" — events vanish without a trace.

---

### P12: Lock Discipline for OMS State Mutations
**Statement:** An `RLock` must be held only for state mutations (order book writes, position updates), never for broker I/O, event publishing, or network calls.
**Rationale:** Holding a lock during I/O risks deadlock (network timeout blocks all other threads) and starves stream callbacks that need to update positions on tick arrival.
**Current Evidence:** `tests/architecture/test_stream_oms_lock_discipline.py` — asserts `PositionManager` uses `threading.RLock`, `OrderManager` uses `_lock`, and lifecycle book writes occur under `with lock`.
**Violation Example:** Holding `self._lock` across a `broker.cancel_order()` network call, blocking all other OMS operations until the HTTP response arrives.

---

### P13: Single Event-Loop Boundary
**Statement:** Only `src/runtime/event_loop.py` may call `asyncio.new_event_loop()`. All other modules must use `run_coro_sync`, `get_runtime_loop`, or `new_dedicated_loop`.
**Rationale:** Scattered event-loop creation causes orphaned loops, inconsistent scheduling, and subtle deadlocks. A single boundary makes loop ownership auditable.
**Current Evidence:** `tests/architecture/test_concurrency_boundary.py` — greps `src/` for `new_event_loop(` outside `runtime/event_loop.py` and fails on any stray call site. `src/runtime/event_loop.py` is the sole sanctioned module.
**Violation Example:** Calling `asyncio.new_event_loop()` inside an infrastructure adapter to "just run one coroutine," creating a second unmanaged loop in the process.

---

### P14: Fail-Closed Production Configuration
**Statement:** Production and staging environments must validate safety gates at boot. `AUTH_MODE=api_key` is required; `RISK_FAIL_OPEN` and `SKIP_PARITY_GATE` are forbidden.
**Rationale:** Fail-open configuration in production is a silent time-bomb — the system runs without authentication or risk checks until a loss event surfaces the misconfiguration.
**Current Evidence:** `src/runtime/production_config.py` — `validate_production_config()` raises `RuntimeError` if production has `AUTH_MODE != "api_key"`, `RISK_FAIL_OPEN=1`, or `SKIP_PARITY_GATE=1`.
**Violation Example:** Deploying with `RISK_FAIL_OPEN=1` to "test faster" and forgetting to remove it, allowing orders to bypass all risk checks on the production broker account.

---

### P15: Anti-Corruption Layer for Broker Status Strings
**Statement:** Broker-specific status strings must be mapped to canonical domain enums through an anti-corruption layer (ACL). Domain code must never interpret raw broker strings.
**Rationale:** Every broker uses different status vocabulary ("complete", "rejected", "cancelled", "triggered pending"). Without normalization, status comparison logic proliferates and breaks.
**Current Evidence:** `src/brokers/common/acl.py` (referenced by `tests/architecture/test_broker_kernel_guardrails.py`) — maps broker wire strings to canonical `OrderStatus`/`ConnectionStatus` enums.
**Violation Example:** Writing `if raw_status == "complete":` inside the OMS order lifecycle instead of routing through the ACL mapper first.

---

### P16: Capability Enforcement at Startup
**Statement:** Broker capabilities must be validated at connection startup. The system must refuse to proceed if required capabilities are missing.
**Rationale:** Running with missing capabilities leads to runtime `AttributeError` or silent no-ops when the code expects a feature (e.g., depth data) that the broker doesn't provide.
**Current Evidence:** `src/brokers/common/capabilities_validator.py` (referenced by `tests/architecture/test_broker_kernel_guardrails.py`) — validates `BrokerCapabilities` against declared requirements at startup.
**Violation Example:** Connecting to a broker that doesn't support `supports_option_chain` but proceeding anyway, then crashing when the strategy engine requests the chain.

---

### P17: No Pandas in the Domain Layer
**Statement:** Top-level pandas imports are forbidden in `src/domain/`. Domain modules must be importable without pandas in `sys.modules`. Lazy imports in export adapters are permitted.
**Rationale:** Pandas is a 30MB dependency that pollutes cold-start time and creates implicit data-mutation patterns. Domain models must be pure Python to stay testable and fast.
**Current Evidence:** `tests/architecture/test_domain_no_pandas_import.py` — AST-scans all domain files for top-level `import pandas` and also proves core domain modules import successfully with pandas absent from `sys.modules`.
**Violation Example:** Adding `import pandas as pd` at the top of `domain/portfolio/portfolio.py` to compute a `to_dataframe()` method directly on the aggregate root.

---

### P18: Token Redaction in Logs
**Statement:** All log output must pass through a `TokenRedactionFilter` that scrubs access tokens, API keys, passwords, and other secrets before they reach log sinks.
**Rationale:** Log aggregation systems (ELK, CloudWatch) are often shared. A leaked bearer token in logs is a credential-compromise event — even in development environments.
**Current Evidence:** `src/infrastructure/logging_config.py` — `TokenRedactionFilter` applies 9 regex patterns to every log message and structured extras; `configure_logging()` installs it by default.
**Violation Example:** Using `logger.debug("Auth response: %s", response.text)` where `response.text` contains an `access_token` — the filter catches this, but the pattern exists to protect against exactly this case.

---

### P19: Test Doubles Use Protocol Fakes, Not MagicMock
**Statement:** All test doubles must implement Protocol interfaces as dataclass fakes. `unittest.mock.MagicMock` is forbidden for OMS, risk, reconciliation, and orchestrator doubles.
**Rationale:** MagicMocks accept any attribute access and method call — they cannot fail for missing interface methods. Protocol fakes fail fast when the interface drifts, catching integration issues at test time.
**Current Evidence:** `tests/fakes/fake_oms.py` — `FakeRiskManager`, `FakePositionManager`, `FakeOrderManager`, `FakeReconciliationService`, `FakeExecutionAdapter`, `FakeBrokerGateway` all implement Protocol interfaces from `application.oms.protocols`. `tests/fakes/fake_trading.py` — `FakeTradingOrchestrator` implements `ITradingOrchestrator`.
**Violation Example:** `mock_om = MagicMock()` followed by `mock_om.place_order.return_value = OrderResult(success=True)` — this test would pass even if `OrderManager` changed `place_order`'s signature entirely.

---

### P20: Architecture Tests Are Static AST Analysis
**Statement:** Architecture invariants must be enforced by static AST analysis at test time, not by runtime assertions or code reviews alone.
**Rationale:** Runtime assertions only catch violations when the code path executes. AST analysis catches violations at import time — every file is checked, even if the function is never called in tests.
**Current Evidence:** `tests/architecture/` directory — `test_domain_isolation.py` (AST walks imports), `test_domain_no_pandas_import.py` (AST scans top-level imports), `test_no_broker_name_branching.py` (regex + AST scan), `test_concurrency_boundary.py` (grep-based static analysis).
**Violation Example:** Replacing the AST-based domain isolation test with a runtime assertion inside `domain/__init__.py` that only fires when the package is imported — a module that's never imported would pass silently.

---

## Principle Index

| ID | Principle | Primary Enforcement |
|----|-----------|-------------------|
| P01 | Domain Layer Isolation | `test_domain_isolation.py` |
| P02 | No Broker-Name Branching | `test_no_broker_name_branching.py` |
| P03 | Gateway Surface Freeze | `test_gateway_surface_freeze.py` |
| P04 | Money Paths Fail Closed | `test_fail_closed_capital_paths.py` |
| P05 | Single OMS Per Process | `application/oms/composition.py` |
| P06 | Record-Then-Submit | `application/oms/ledger_outbox.py` |
| P07 | Strategy Pipeline Parity | `application/strategy_engine/engine.py` |
| P08 | Single Service Core | `brokers/services/core.py` |
| P09 | Protocol-Based Interfaces | `domain/ports/protocols.py` |
| P10 | Copy-On-Publish Events | `infrastructure/event_bus/event_bus.py` |
| P11 | DLQ Never Swallows Failures | `infrastructure/event_bus/event_bus.py` |
| P12 | Lock Discipline | `test_stream_oms_lock_discipline.py` |
| P13 | Single Event-Loop Boundary | `runtime/event_loop.py` |
| P14 | Fail-Closed Production Config | `runtime/production_config.py` |
| P15 | Anti-Corruption Layer | `brokers/common/acl.py` |
| P16 | Capability Enforcement | `brokers/common/capabilities_validator.py` |
| P17 | No Pandas in Domain | `test_domain_no_pandas_import.py` |
| P18 | Token Redaction in Logs | `infrastructure/logging_config.py` |
| P19 | Protocol Fakes, Not MagicMock | `tests/fakes/fake_oms.py` |
| P20 | Static AST Architecture Tests | `tests/architecture/` |
