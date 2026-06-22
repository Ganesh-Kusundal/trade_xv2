# TradeXV2 — Comprehensive Architecture & Engineering Review

**Review Date:** 2026-06-22  
**Review Scope:** End-to-end production-grade quantitative trading platform  
**Reviewers:** Principal Software Engineer, Staff Architect, Quant Trading Architect, Low-Latency Systems Engineer, Event-Driven Architecture Expert, Distributed Systems Expert, SRE, QA/Test Automation Architect, Security Architect, Data Platform Architect, Frontend Architect, DevOps/Cloud Architect, Performance Engineering Specialist

---

## Executive Summary

TradeXV2 is an ambitious, well-structured Python-based quantitative trading platform with a React frontend. The foundation shows strong software engineering discipline: ADR-001 domain single-source is executed excellently, the event bus design is thread-safe with DLQ support, and the state machine pattern is generic and well-documented. However, **the platform is NOT production-ready for live trading with real money.** Critical security gaps (zero API authentication, public trading endpoints), reliability risks (AsyncEventBus DLQ is broken by a `TypeError`, replay is a stub), data loss risks (no live tick ingestion), and architectural violations (import direction broken in multiple places) collectively create a high probability of production incidents.

**Production Readiness Score: 3.2/10**

---

## 1. Architecture Review Report

### 1.1 Overall Architecture & Bounded Contexts

**Identified Bounded Contexts:**
- Core Domain (`brokers/common/core/`) — canonical types, state machines, instruments
- Execution/OMS (`brokers/common/oms/`) — orders, positions, risk, reconciliation
- Event Infrastructure (`brokers/common/event_bus/`) — in-memory bus, DLQ, event log
- Broker Adapters (`brokers/dhan/`, `brokers/upstox/`, `brokers/paper/`) — broker-specific gateways
- Data Lake (`datalake/`) — Parquet storage, DuckDB catalog, research API
- Analytics (`analytics/`) — pipelines, scanners, strategies, replay, backtest
- CLI/TUI (`cli/`) — user interface, composition root, observability
- API Server (`datalake/api/`) — FastAPI routers, WebSocket bridges

**Strengths:**
- ADR-001 is rigorously enforced via ruff banned-API rules
- Immutable value objects throughout core domain
- Correlation ID propagation via thread-local context
- Re-entrancy guards in OrderManager/PositionManager

### 1.2 Service Decomposition — God Classes Detected

| Module | Lines | Severity | Issue |
|--------|-------|----------|-------|
| `brokers/dhan/factory.py` (`BrokerFactory.create`) | 414 | HIGH | Creates auth, HTTP client, circuit breakers, token scheduler, WebSocket services — violates SRP |
| `brokers/dhan/connection.py` (`DhanConnection`) | 26 adapter imports | HIGH | Hardcodes 20+ adapter imports; no registry pattern |
| `cli/services/broker_service.py` (`BrokerService`) | 365 | MEDIUM | Facade + orchestrator hybrid; manages gateway, OMS, lifecycle, observability |
| `datalake/gateway.py` (`DataLakeGateway`) | 560 | MEDIUM | Data access + batch operations + resampling + caching |
| `brokers/common/oms/context.py` (`TradingContext`) | 477 | MEDIUM | 15+ constructor parameters; wires event bus, OMS, reconciliation, DLQ |
| `brokers/common/oms/order_manager.py` (`OrderManager`) | 521 | MEDIUM | Order placement, cancellation, trade recording, event publishing, state machine |

### 1.3 Coupling/Cohesion — Critical Import Direction Violations

**Documented Rules (`docs/IMPORT_DIRECTION_RULES.md`):**
```
cli → brokers → datalake → analytics
```

| Violation | File | Line | Severity |
|-----------|------|------|----------|
| `analytics` → `cli` | `analytics/replay/engine.py` | 40 | CRITICAL |
| `analytics` → `cli` | `analytics/replay/oms_bridge.py` | 13 | CRITICAL |
| `brokers/common` → `analytics` | `brokers/common/orchestrator/trading_orchestrator.py` | 42-45 | CRITICAL |
| `brokers/common` → `analytics` | `brokers/common/orchestrator/models.py` | 23-24 | CRITICAL |
| `datalake` → `analytics` | `datalake/fast_backtest.py` | 16-25 | CRITICAL |
| `datalake/api` → `analytics` | `datalake/api/routers/backtest.py` | 67,71,81 | HIGH |
| `datalake/api` → `analytics` | `datalake/api/routers/replay.py` | 148-150 | HIGH |

### 1.4 CQRS / Event Sourcing Assessment

**Not true event sourcing.** The system has:
- ✅ Immutable events
- ✅ Append-only event log
- ✅ Replay capability
- ❌ No state reconstruction from events alone
- ❌ No event versioning/schema migration
- ❌ No snapshots
- ❌ No projection system

The event log is for **audit and crash recovery**, not event sourcing.

---

## 2. Quant Platform Review Report

### 2.1 Trading Readiness Assessment

| Capability | Status | Gap |
|------------|--------|-----|
| Multi-strategy execution | Partial | Only MomentumStrategy and BreakoutStrategy built-in; no hot-reload |
| Multi-broker execution | Partial | Dhan + Upstox adapters exist; paper broker stubbed |
| Scanner development | ✅ | ScannerRunner with parallel execution; BaseScanner + event publishing |
| Signal generation | Partial | StrategyPipeline exists; orchestrator imports analytics (coupling risk) |
| Portfolio management | Partial | PositionManager + ReconciliationService exist |
| Risk management | Partial | RiskManager + kill switch exist; `enforce_state_transitions=False` by default |
| Position sizing | Basic | CapitalProvider exists but manual |
| Order routing | ✅ | OrderManager abstracts routing |
| Event replay | Partial | ReplayEngine is stubbed (`_execute_replay` returns empty result) |
| Backtesting | Partial | BacktestEngine exists; `datalake/fast_backtest.py` violates import rules |
| Walk-forward testing | ❌ | Not implemented |
| Paper trading | Partial | `brokers/paper/paper_gateway.py` exists but not fully wired |
| Live trading | ❌ | Missing auth, permission checks, rate limiting on API |
| Performance analytics | Basic | PnL calculator + DailyPnlResetScheduler exist |

### 2.2 Risk Management Gaps

- `OrderManager.enforce_state_transitions=False` (default) — illegal transitions accepted in production
- `PositionManager.enforce_state_transitions=False` (default)
- No unified circuit breaker for Upstox (only 1 breaker vs Dhan's 3)
- No position limit enforcement at OMS level
- No portfolio-level concentration risk checks

---

## 3. Event-Driven Design Report

### 3.1 Event Model & Contracts

- 40+ canonical `EventType` enum values defined
- `EVENT_PAYLOADS` catalog is documentation-only; validation opt-in (`validate=False`)
- **No event schema versioning**

### 3.2 Critical Bugs Found

| # | Bug | File | Severity |
|---|-----|------|----------|
| 1 | `AsyncEventBus` DLQ call is invalid — `push(event, exc)` instead of `push_failure(event, handler_id, exc)` | `async_event_bus.py:477` | CRITICAL |
| 2 | `AsyncEventBus` generates `DomainEvent.now()` without `sequence_number` — all async events get `seq=0` | `async_event_bus.py:373` | HIGH |
| 3 | `AsyncEventBus` has no `replay_mode` — cannot participate in crash-recovery replay | `async_event_bus.py` | HIGH |
| 4 | `ReconciliationService.finally: publish()` masks original reconciliation error | `reconciliation_service.py:180-205` | HIGH |
| 5 | Trade ledger marked before order state mutated — crash between lines leaves ledger "processed" but position manager never saw TRADE_APPLIED | `order_manager.py:330-352` | MEDIUM |
| 6 | `_replay_log_into_oms()` does not reset `_logging_enabled=False` on exception | `context.py:466-476` | MEDIUM |
| 7 | `RECONCILIATION_COMPLETED` published as raw string instead of enum value | `reconciliation_service.py:200` | MEDIUM |
| 8 | Sequence counter assigned before dispatch lock — concurrent publishes can have mismatched order vs persistence | `event_bus.py:237-245` | MEDIUM |

### 3.3 Dead Event Types

`RECONCILIATION_DRIFT`, `RECONCILIATION_OK`, `INDEX_QUOTE`, `OPTION_CHAIN`, `SIGNAL_GENERATED` — defined in enum but never published.

---

## 4. Code Smell Report

### 4.1 God Classes / God Services
- `BrokerFactory.create()` — 414 lines (SRP violation)
- `DhanConnection` — 26 adapter imports (abstraction violation)
- `DataLakeGateway` — 560 lines (data access + batch + resampling + caching)
- `TradingContext` — 15+ constructor parameters

### 4.2 Cyclic Dependencies
- `BrokerCommon.orchestrator → analytics` (immediate cycle risk: analytics → datalake → datalake.api → brokers.common)
- `analytics/replay → cli.services.compose` (direct cycle)

### 4.3 Primitive Obsession
- `correlation_id=f"http-{datetime.now().isoformat()}"` in API router — no binding to authenticated principal
- `TradeIdKey` is a full frozen dataclass (good), but many downstream types use raw strings

### 4.4 Shotgun Surgery
- `DhanConnection` requires modification for every new adapter capability
- Hardcoded broker dispatch in `broker_registry.py` instead of true entry-point discovery

### 4.5 Duplicate Code
- Rate limiter: Dhan custom throttle vs Upstox `UpstoxRateLimiter` vs common `TokenBucketRateLimiter` — common layer unused
- `hash()` function duplicated in `mockMarket.ts` and `symbols.ts`
- Button styling duplicated across ChartToolbar, ReplayPanel

### 4.6 Over-Engineering
- `MultiBucketRateLimiter` exists but is unused in production adapters
- Three-tier circuit breaker split (read/write/admin) is excellent but only Dhan uses it

### 4.7 Under-Engineering
- No schema validation on event payloads
- `clear()` on `ProcessedTradeRepository` doesn't truncate persistence file
- `BrokerService` is a 365-line monolith with no interfaces

---

## 5. Testing Gap Analysis

### 5.1 Missing Test Coverage

| Missing Tests | Severity |
|---------------|----------|
| No tests for `risk/`, `strategy/`, `backtesting/`, `replay/`, `portfolio/`, `market_data/` | HIGH |
| `AsyncEventBus` — no dedicated unit tests | HIGH |
| `UpstoxHttpClient` — no retry/token-refresh tests | HIGH |
| `DhanDepth200Feed` cache key bug (`int(security_id)` vs string key) — no test | HIGH |
| WebSocket load/stress tests — not in CI | MEDIUM |
| DNS/tcp-level partition chaos tests | MEDIUM |
| Full replay orchestrator end-to-end (stub returns empty result) | HIGH |
| `TradingOrchestrator` end-to-end signal-to-order flow | MEDIUM |
| `LoadTestRunner` race condition (unguarded shared state) | LOW |

### 5.2 Test Quality Issues

| Issue | File | Severity |
|-------|------|----------|
| `pytest.skip()` turns security tests into no-ops | `test_security_findings.py:52,82` | HIGH |
| `pytest.skip()` on architecture ABC compliance tests | `test_gateway_abc_compliance.py:58+` | HIGH |
| `time.sleep()` in test code causing flakiness | Multiple files | MEDIUM |
| Unimplemented `test_no_token_in_log_messages` (pass with no logic) | `test_security_findings.py:176-180` | MEDIUM |

### 5.3 Coverage Configuration

- `pyproject.toml` coverage source omits `tests/e2e`, `tests/api`, `tests/architecture`, `tests/performance`, `brokers/upstox`
- `fail-under=60` with no per-module thresholds
- Performance tests **not excluded from PR CI**

---

## 6. Reliability Assessment

### 6.1 Top Failure Modes

| Failure Mode | Impact | Recovery |
|--------------|--------|---------|
| `AsyncEventBus` DLQ TypeError on ANY async handler failure | Async handlers fail silently; DLQ non-functional | Must restart process; failure is permanent until fix |
| Event log append blocks publisher thread | Tick-to-handler latency spikes to fsync times | No automatic rollback; latency spikes until disk catches up |
| `ReplayEngine._execute_replay` stub | Replay returns empty results | No recovery; feature is broken |
| Upstox WS gives up after 5 reconnects | Market data stream permanently dead | Requires manual gateway recreation |
| Upstox portfolio stream single-recv break | Permanent positions/holdings silence | Manual restart of portfolio stream |
| Token refresh fails silently in Upstox | 401 on WebSocket reconnect; stream dies | No alerting; silent failure |
| `ProcessedTradeRepository` permission race | Token files world-readable | Manual permission fix after discovery |

### 6.2 Single Points of Failure

1. `AsyncEventBus` — single dispatch worker; if it crashes, all async event processing stops
2. `UpstoxMarketDataV3Multiplexer` — reset on 5 reconnect failures; no escalation to caller
3. `DhanHttpClient` — single client shared across all adapters; one broad failure affects all endpoints
4. `runtime/event-log/` — single SQLite WAL file for crash recovery; disk full = data loss
5. `DataLakeGateway` — singleton; all historical queries go through one process

---

## 7. Security Assessment

### 7.1 Critical Vulnerabilities

| # | Vulnerability | Severity | File |
|---|---------------|----------|------|
| 1 | Zero API authentication on FastAPI | CRITICAL | `datalake/api/main.py:141-172` |
| 2 | Public order placement endpoint | CRITICAL | `datalake/api/routers/orders.py:138-192` |
| 3 | Public kill-switch toggle | CRITICAL | `datalake/api/routers/risk.py:32-41` |
| 4 | Unauthenticated token webhook (Upstox) | CRITICAL | `brokers/upstox/auth/token_webhook_controller.py:54-84` |
| 5 | Rate limiting disabled by default | HIGH | `datalake/api/config.py:54` |
| 6 | `.env.local` loaded without permission check | HIGH | `cli/main.py:29-31` |
| 7 | Plaintext token written to `.env` on refresh | HIGH | `brokers/dhan/token_manager.py:98-181` |
| 8 | `allow_live_orders` defaults to `True` | HIGH | `brokers/upstox/auth/config.py:42` |
| 9 | Mutable audit logs (no append-only enforcement) | HIGH | `brokers/common/logging_config.py` |
| 10 | SQL injection via unparameterized DESCRIBE | HIGH | `analytics/views/manager.py:576` |
| 11 | Token file permission race (write before chmod) | HIGH | `brokers/common/core/auth.py:192-214` |
| 12 | `reload=True` in production server launcher | MEDIUM | `api_server.py:108` |
| 13 | Response bodies logged on 4xx (PII leak) | MEDIUM | `brokers/dhan/http_client.py:319,324` |
| 14 | CORS allow_credentials=True with dev origins | LOW | `datalake/api/config.py:45-51` |

**Key Finding:** Any attacker who can reach port 8000 can place live trades, disable risk controls, and steal positions. The platform has **zero network-layer authorization**.

---

## 8. Performance Assessment

### 8.1 Latency Bottlenecks

| Bottleneck | Location | Severity |
|-----------|----------|----------|
| EventBus publish sync lock ×2 + EventLog I/O on publisher thread | `event_bus.py:240-255` | P0 |
| Dhan backfill blocks WS receive loop | `dhan/websocket.py:466-499` | P0 |
| `ProcessedTradeRepository.fsync()` per trade in OMS critical path | `processed_trade_repository.py:349-354` | P0 |
| Dhan PollingMarketFeed sequential REST per instrument | `dhan/websocket.py:1053-1091` | P0 |
| DataLake `history(list)` not using DuckDB batch path | `gateway.py:148-173` | P1 |
| Dhan 1000 instrument cap per connection (no auto-sharding) | `dhan/websocket.py:158` | P1 |
| LoadTestRunner unguarded shared state | `cli/load_testing/runner.py:34-98` | P1 |
| Upstox `AsyncEventBus` unused by production paths | Platform-wide | P0 |

### 8.2 Memory & Concurrency

- Dhan `_last_tick_time` was unbounded until P3 cleanup (every 100 messages, 30-min TTL)
- `MarketConnectionManager` uses plain `dict` without locks — race on concurrent subscribe/disconnect
- `datalake/updater.py` read-modify-write without file locking — concurrent updates corrupt Parquet

---

## 9. Data Platform Report

### 9.1 Critical Data Loss Risks

1. **Live tick loss on restart** — `DataLakeGateway.stream()` raises `NotImplementedError`. No real-time Parquet writer exists.
2. **Concurrent updater corruption** — `datalake/updater.py:112-118` has no file locking
3. **Depth data ephemeral** — order book data lives in memory only; no persistence
4. **Clock drift / out-of-order events** — no monotonic clock usage; no timestamp validation against broker-server time
5. **No dedup in live WebSocket path** — broker duplicates published to EventBus without filtering

### 9.2 Schema Issues

- `datalake/schema.py` line 35: `TRADING_MINUTES_PER_DAY = 375` but arithmetic yields 376
- No schema evolution strategy for adding new columns
- No documentation for Parquet partitioning strategy beyond auto-discovery

---

## 10. Frontend Architecture Report

### 10.1 Issues

| Issue | File | Severity |
|-------|------|----------|
| `ChartPanel` acts as god component (orchestrates hooks, replay, errors) | `ChartPanel.tsx:31-154` | HIGH |
| Duplicate quote polling (Sidebar + TopBar + ChartPanel each fetch same symbol) | 3 files | HIGH |
| Replay stale closure on `speed`/`cursorT` | `ReplayPanel.tsx:65-82` | HIGH |
| Interval churn — `useCandles` interval recreated every candle append | `ChartPanel.tsx:46-67` | HIGH |
| No WS reconnection logic | `client.ts:190-207` | MEDIUM |
| Split-brain replay state (store `replayOpen` vs local `replayActive`) | `ChartPanel.tsx:37-44` | MEDIUM |
| No primitive component library | App-wide | MEDIUM |
| Stale `vite.config.js` alongside `vite.config.ts` | `frontend/` root | LOW |

---

## 11. Repository Organization Report

### 11.1 Critical Issues

- **`pyproject.toml` package discovery includes non-existent top-level packages:** `market_data`, `oms`, `portfolio`, `risk`, `strategy`, `backtesting`, `replay`
- **Top-level scripts clutter root:** `test_cli_speed.py`, `api_server.py`, `check_data_freshness.py`, `check_data_quality.py`, `test_populate_cache.py`
- **`archive/` directory** contains dead frontend snapshot (should not be in repo)
- **`temp/config/`** contains credential files that should be `.gitignore`d
- **`conftest.py` at root** instead of `tests/conftest.py`
- **`tradex` launcher at root** instead of `scripts/tradex`

---

## 12. Production Readiness Scorecard

| Area | Score (1-10) | Justification |
|------|:---:|---------------|
| Architecture | 4 | Foundation is solid but import violations + god classes break boundaries |
| Quant Design | 5 | Strategy/scanner abstractions exist but live trading path is incomplete |
| Code Quality | 5 | Good typing and conventions but god classes, cyclic deps, and 411 mypy errors |
| Testing | 5 | Extensive unit tests but critical gaps in security, replay, async bus, E2E |
| Reliability | 3 | AsyncEventBus DLQ broken; restart can lose state; no circuit breakers on WS |
| Scalability | 4 | EventBus single-lock bottleneck; 1000 instrument hard cap; no auto-sharding |
| Security | 1 | Zero API auth; public trading endpoints; secrets written to disk without enforcement |
| Performance | 4 | Sync EventBus blocks publisher; backfill blocks WS loop; PollingMarketFeed is O(n²) |
| Maintainability | 4 | Import direction rules violated; god classes; top-level scripts scattered |
| Operational Readiness | 2 | No Docker; no monitoring stack; mutable audit logs; no rollback procedures |

**Overall Production Readiness Score: 3.2/10**

---

## Top 20 Risks

1. **Zero API authentication** — any local process can place live trades
2. **AsyncEventBus DLQ TypeError** — async handler failures crash DLQ silently
3. **ReplayEngine stub** — `_execute_replay` returns empty result; backtest-on-replay is broken
4. **No live tick persistence** — all real-time data lost on restart
5. **Upstox WS gives up after 5 reconnects** — permanent market data blackout
6. **Upstox portfolio stream dies on first recv error** — no reconnect
7. **Token refresh race in Upstox** — no WS token refresh on reconnect
8. **Dhan backfill blocks WS thread** — post-reconnect tick blackout
9. **ProcessedTradeRepository fsync per trade** — OMS latency spike per fill
10. **Concurrent updater corruption** — no file locking on Parquet writes
11. **Import direction violations** — cyclic dependency risk in orchestrator
12. **State enforcement disabled by default** — illegal transitions accepted
13. **Rate limiting disabled on API** — flooding/layering attacks possible
14. **Mutable audit logs** — operator can delete trading history
15. **No event schema versioning** — breaking changes silently corrupt consumers
16. **Depth cache key bug in depth_200.py** — unsubscribe pops wrong key; cache leak
17. **Corrupt JSON silently skipped on replay** — no visibility into data loss
18. **`.env.local` loaded without permission check** — credentials readable by other users
19. **`allow_live_orders` defaults True** — sandbox can accidentally execute live trades
20. **No DNS/tcp partition chaos tests** — broker outage handling unverified

---

## Top 20 Improvements

1. Add FastAPI authentication middleware (HTTPBearer or JWT)
2. Fix `AsyncEventBus.push()` signature to correct DLQ call
3. Implement `replay_mode` and `sequence_number` in `AsyncEventBus`
4. Remove `analytics → cli` import; extract replay orchestration into proper layer
5. Move `brokers/common/orchestrator` to `analytics/orchestrator` (fix direction violation)
6. Enable state enforcement by default in OrderManager/PositionManager
7. Enable rate limiting on FastAPI API (slowapi or similar)
8. Add file locking to `datalake/updater.py`
9. Implement live tick ingestion to Parquet or write-ahead log
10. Fix Dhan backfill to run in thread pool (non-blocking)
11. Add auto-sharding for Dhan WebSocket (split across N connections at 1000 instruments)
12. Replace PollingMarketFeed sequential REST with batch calls
13. Add circuit breaker to Upstox WS reconnect path
14. Fix Upstox portfolio stream reconnect
15. Add token refresh on Upstox WS reconnect
16. Buffer ProcessedTradeRepository disk writes (batch fsync every N trades or T ms)
17. Add event schema versioning with backward-compat validation
18. Convert all top-level scripts to proper CLI subcommands
19. Add skeleton/spinner loading components to frontend
10. Unify quote polling into single Zustand store slice

---

## Prioritized Action Plan

### Quick Wins (1–2 Days)

1. **Fix `AsyncEventBus` DLQ TypeError** (1 file, 1 line) — prevents all async handler failures from being silently swallowed
2. **Add FastAPI authentication dependency** (1 file, ~30 lines) — blocks public access to trading endpoints
3. **Enable `replay_mode` in `AsyncEventBus`** (3 files, ~20 lines) — enables crash-recovery replay for async events
4. **Fix `allow_live_orders` default to `False`** (1 line) — prevents accidental live order placement in sandbox
5. **Add `.env` permission validation before load** (1 file, ~15 lines) — warns if secrets are world-readable
6. **Fix `TestSecretsNotLogged::test_no_token_in_log_messages`** (remove `pytest.skip()`) — unblocks security regression detection
7. **Remove stale paperback `vite.config.js`** — eliminates tooling confusion
8. **Move top-level scripts to `scripts/`** (git mv 5 files) — cleans root directory

### Medium-term Improvements (1–4 Weeks)

9. **Refactor `DhanConnection`** — extract adapter registry pattern; eliminate hardcoded imports
10. **Refactor `BrokerFactory.create()`** — split into builder classes (AuthBuilder, HttpBuilder, WsBuilder)
11. **Fix `datalake/fast_backtest.py`** import violations — use dependency injection instead of direct imports
12. **Move `brokers/common/orchestrator` to `analytics/orchestrator`** — fixes critical import direction violation
13. **Fix DataLake `history(list)` to use DuckDB batch path** — 2–10x improvement for multi-symbol history
14. **Add file locking to `datalake/updater.py`** — prevents concurrent updater corruption
15. **Implement live tick ingestion to EventLog** — eliminates data loss on restart
16. **Add Upstox WS token refresh** — handles token expiry mid-session
17. **Fix Upstox portfolio stream reconnect** — permanent death on first error
18. **Add circuit breaker to Upstox WS** — protects against rapid reconnect storms
19. **Add schema versioning to `DomainEvent`** — enables safe event payload evolution
20. **Add WebSocket reconnection + backoff to frontend `client.ts`** — prevents stale UI on network blips
21. **Unify frontend quote polling into Zustand store** — eliminates duplicate requests per symbol
22. **Fix `OrderManager`/`PositionManager` state enforcement defaults to `True`**
23. **Add file-locking and schema evolution to Parquet batch writes**
24. **Implement auto-sharding for Dhan WebSocket** — supports >1000 instruments

### Long-term Strategic Improvements (1–6 Months)

25. **Replace sync `EventBus` with async dispatch** — eliminates publisher blocking
26. **Build proper broker plugin discovery** — replace hardcoded string dispatch with entry-point registry
27. **Implement event sourcing** — projections + snapshots; enable true state rebuild from log
28. **Add append-only audit log sink** — ship critical events to SIEM/WORM for compliance
29. **Implement Docker + Docker Compose** — reproducible deployments with health checks
30. **Add monitoring stack** — Prometheus + Grafana for EventBus latency, WS reconnects, OMS state, PnL
31. **Build component library** — extract Button, Spinner, Skeleton into `frontend/src/components/ui/`
32. **Implement proper DI container** — replace `build_runtime()` procedural function with real composition root
33. **Add network chaos engineering** — DNS failure, partition, broker blackhole tests
34. **Build walk-forward optimization** — gap in quantitative tooling
35. **Implement position sizing + risk engine** — portfolio-level concentration checks
36. **Add ZeroMQ or Kafka** — replacement for in-memory bus for multi-process scale

---

## Deliverables Checklist

- [x] Executive Summary
- [x] Architecture Review Report
- [x] Quant Platform Review Report
- [x] Code Smell Report
- [x] Testing Gap Analysis
- [x] Reliability Assessment
- [x] Security Assessment
- [x] Performance Assessment
- [x] Refactoring Roadmap
- [x] Production Readiness Scorecard
- [x] Prioritized Action Plan
