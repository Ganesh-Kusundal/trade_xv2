# TradeXV2 — Remediation Execution Plan

## Approach

We will fix all issues found in the comprehensive review across 5 phases, using specialized multi-agent teams. Each phase has clear deliverables, test gates, and exit criteria.

---

## Phase 0: Critical Safety Fixes (Day 1-2)

**Team:** Engineer + QA + Reviewer

| # | Task | Files | Agent Team | Est. Time |
|---|------|-------|------------|-----------|
| **P0.1** | Fix options bid/ask: return `None` instead of `0.0`, add docstring that bid/ask unavailable from OHLCV | `datalake/api/routers/options.py` | Engineer | 30 min |
| **P0.2** | Disable MD5 feature cache in backtest path to prevent look-ahead bias | `analytics/pipeline/pipeline.py`, `datalake/gateway.py` | Engineer + Reviewer | 2 hours |
| **P0.3** | Parameterize all DuckDB f-string SQL queries | `datalake/gateway.py`, `datalake/api/routers/options.py` | Engineer + Security | 2 hours |
| **P0.4** | Fix quote() bid/ask synthesis in DataLakeGateway | `datalake/gateway.py` | Engineer | 30 min |
| **P0.5** | Enable `enforce_state_transitions=True` by default | `brokers/common/oms/order_manager.py` | Engineer | 15 min |
| **P0.6** | Add ProcessedTradeRepository singleton enforcement | `brokers/common/oms/order_manager.py` | Engineer | 1 hour |
| **P0.7** | Add Cache-Control headers to `/candles` and `/quote` endpoints | `datalake/api/routers/market.py` | Engineer | 30 min |
| **P0.8** | Replace `df.iterrows()` with vectorized dict/list comprehension | `datalake/api/routers/market.py` | Engineer + Reviewer | 1 hour |

**Exit Criteria:**
- [ ] All P0.1-P0.8 merged
- [ ] Existing tests pass
- [ ] Code review completed for each change

---

## Phase 1: OMS-API Integration (Day 2-5)

**Team:** Principal Engineer + Staff Architect + QA

| # | Task | Files | Agent Team | Est. Time |
|---|------|-------|------------|-----------|
| **P1.1** | Wire `TradingContext` into FastAPI `lifespan` so OMS is single authority | `datalake/api/main.py`, `datalake/api/lifecycle.py` | Principal Engineer | 3 days |
| **P1.2** | Replace global `_service_registry` dict with FastAPI dependency injection | `datalake/api/deps.py` | Staff Architect | 2 days |
| **P1.3** | Wire remaining stub endpoints (holdings, pnl, modify, cancel) through real OMS | `datalake/api/routers/*.py` | Engineer | 2 days |
| **P1.4** | Wire replay sessions through real `ReplayEngine` | `datalake/api/routers/replay.py` | Engineer | 2 days |
| **P1.5** | Wire backtest endpoints through real `BacktestEngine` | `datalake/api/routers/backtest.py` | Engineer + Quant | 2 days |

**Exit Criteria:**
- [ ] `GET /orders/{id}`, `PUT /orders/{id}`, `DELETE /orders/{id}` work through OMS
- [ ] `GET /portfolio/holdings`, `/summary`, `/pnl` work through real services
- [ ] Replay play/pause/seek drives actual ReplayEngine
- [ ] Backtest runs produce real results
- [ ] All API contract tests pass
- [ ] Code review completed

---

## Phase 2: Test Infrastructure (Day 3-7)

**Team:** QA Architect + Engineer + Reviewer

| # | Task | Files | Agent Team | Est. Time |
|---|------|-------|------------|-----------|
| **P2.1** | Add API contract tests that verify real behavior (not just route existence) | `tests/api/test_*.py` | QA + Engineer | 3 days |
| **P2.2** | Add concurrency tests for EventBus (multi-publisher, multi-subscriber) | `tests/test_event_bus.py` | QA | 1 day |
| **P2.3** | Add concurrency tests for OrderManager (duplicate trades, parallel orders) | `tests/test_order_manager.py` | QA | 1 day |
| **P2.4** | Add chaos tests (network failure, DB corruption, partial data) | `tests/chaos/test_*.py` | QA + SRE | 2 days |
| **P2.5** | Add CI integration test run (separate workflow with sandbox credentials) | `.github/workflows/integration.yml` | DevOps | 1 day |
| **P2.6** | Add frontend unit tests (vitest) | `frontend/src/**/*.test.tsx` | Frontend | 2 days |

**Exit Criteria:**
- [ ] 20+ API contract tests covering all routers
- [ ] 10+ concurrency tests
- [ ] 5+ chaos test scenarios
- [ ] CI runs integration tests daily
- [ ] Frontend test coverage >30%

---

## Phase 3: Reliability & Performance (Day 5-12)

**Team:** Performance Engineer + SRE + Engineer

| # | Task | Files | Agent Team | Est. Time |
|---|------|-------|------------|-----------|
| **P3.1** | Add circuit breakers to broker HTTP calls | `brokers/common/resilience/circuit_breaker.py` | Engineer + SRE | 2 days |
| **P3.2** | Add bounded queues to WebSocket connections (drop-oldest policy) | `datalake/api/ws/market.py`, `ws/bridge.py` | Performance Engineer | 2 days |
| **P3.3** | Dockerize the application (API + CLI + data volume) | `Dockerfile`, `docker-compose.yml` | DevOps | 1 day |
| **P3.4** | Add structured JSON logging throughout | All modules | Engineer | 2 days |
| **P3.5** | Add `GET /metrics` endpoint with real metrics (orders/sec, trades/sec, latency) | `datalake/api/routers/health.py` | SRE | 2 days |
| **P3.6** | Add data freshness alerting cron job | New scheduled script | Engineer | 1 day |
| **P3.7** | Options Greeks: wire Upstox v3 Greeks API | `datalake/api/routers/options.py` | Engineer + Quant | 2 days |

**Exit Criteria:**
- [ ] Circuit breakers trip on >5s latency
- [ ] WS disconnect on slow client doesn't stall others
- [ ] Docker image builds and runs
- [ ] Metrics endpoint returns real data
- [ ] Data freshness check runs nightly

---

## Phase 4: Refactoring & Pay Down (Day 8-16)

**Team:** Architect + Engineer + Frontend + Reviewer

| # | Task | Files | Agent Team | Est. Time |
|---|------|-------|------------|-----------|
| **P4.1** | Unify `SimulatedTrade` → `Trade`, `SimulatedPosition` → `Position` | `analytics/replay/models.py`, domain models | Architect + Engineer | 2 days |
| **P4.2** | Make `TradingContext` mandatory in `ReplayEngine`, remove `SimulatedPosition` fallback | `analytics/replay/engine.py` | Quant + Engineer | 1 day |
| **P4.3** | Centralize config into single `pydantic-settings` class | New `config/settings.py` | Engineer | 1 day |
| **P4.4** | Add React Error Boundaries | `frontend/src/components/ErrorBoundary.tsx` | Frontend | 1 day |
| **P4.5** | Switch frontend quote from HTTP polling to WebSocket | `frontend/src/hooks/useQuote.ts`, `datalake/api/ws/market.py` | Frontend + Engineer | 3 days |
| **P4.6** | Add real commission model (STT, GST, SEBI, stamp duty) | `analytics/replay/models.py` | Quant | 2 days |
| **P4.7** | Add corporate action handling for backtests | `analytics/backtest/` | Quant | 2 days |
| **P4.8** | Add event versioning + schema registry for EventBus | `brokers/common/event_bus/` | Architect | 2 days |
| **P4.9** | Add API authentication (API key + rate limiting) | `datalake/api/middleware/` | Security + Engineer | 3 days |
| **P4.10** | Add plugin system for strategies and scanners | `analytics/strategy/`, `pyproject.toml` | Architect | 2 days |

**Exit Criteria:**
- [ ] Zero duplicated domain model classes
- [ ] ReplayEngine always uses OMS path
- [ ] Single Settings object replaces all scattered config
- [ ] Frontend uses WebSocket for real-time data
- [ ] Commission model matches Indian broker reality
- [ ] API key authentication gates all endpoints

---

## Phase 5: Quant Platform Hardening (Day 12-20)

**Team:** Quant Architect + Engineer + QA

| # | Task | Files | Agent Team | Est. Time |
|---|------|-------|------------|-----------|
| **P5.1** | Add walk-forward optimization framework | `analytics/backtest/optimizer.py` | Quant | 3 days |
| **P5.2** | Add Monte Carlo simulation for strategy validation | `analytics/backtest/` | Quant | 3 days |
| **P5.3** | Add market impact model (Almgren-Chriss style) | `analytics/backtest/` | Quant | 3 days |
| **P5.4** | Add tick-level data pipeline | `datalake/ticks/` | Engineer | 4 days |
| **P5.5** | Add multi-strategy execution engine | `brokers/common/portfolio/` | Quant + Engineer | 4 days |
| **P5.6** | Add performance regression CI benchmarks | `.github/workflows/benchmarks.yml` | Performance | 2 days |

**Exit Criteria:**
- [ ] Walk-forward analysis works on any strategy
- [ ] Monte Carlo produces confidence intervals
- [ ] Market impact model prevents over-trading illiquid symbols
- [ ] Tick data stored and queryable
- [ ] Multi-strategy allocator works

---

## Execution Summary

| Phase | Focus | Est. Days | Agent Team Size |
|-------|-------|-----------|-----------------|
| **P0** | Critical Safety Fixes | 1-2 | 3 agents |
| **P1** | OMS-API Integration | 3-5 | 3 agents |
| **P2** | Test Infrastructure | 5-7 | 3 agents |
| **P3** | Reliability & Performance | 7-12 | 3 agents |
| **P4** | Refactoring & Pay Down | 10-16 | 4 agents |
| **P5** | Quant Platform Hardening | 14-20 | 3 agents |
| **Total** | | **20-30 days** | |

---

## Immediate Next Actions

Waiting for user approval to begin **Phase 0**:

1. **P0.1** — Fix options bid/ask → `None`  
2. **P0.2** — Disable MD5 feature cache  
3. **P0.3** — Parameterize DuckDB SQL  
4. **P0.4** — Fix DataLakeGateway quote() bid/ask  
5. **P0.5** — Enable enforce_state_transitions  
6. **P0.6** — Add ProcessedTradeRepository singleton  
7. **P0.7** — Add Cache-Control headers  
8. **P0.8** — Replace df.iterrows() with vectorized
