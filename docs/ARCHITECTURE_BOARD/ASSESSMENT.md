# TradeXV2 — Institutional Trading Framework Architecture Assessment

**Board:** Principal Trading Systems Architect, Chief DDD Architect, OMS/EMS Architect, Market Data Architect, Quant Platform Architect, Enterprise Test Architect, Platform Reliability Engineer, DX Architect.

**Date:** 2026-07-09  
**Status:** Board review complete; Phase 0–1 implemented; Phases 2–6 planned.

---

## 1. Executive Architecture Assessment

TradeXV2 is a **broker-agnostic algorithmic trading framework** for Indian exchanges (NSE/BSE/MCX). The stated goal is an institutional-grade, object-oriented platform where developers interact with rich market domain objects (`Equity("NIFTY").quote`, `.buy()`) while broker SDKs, REST, WebSockets, and persistence remain hidden behind ports.

**Verdict:** The **architectural intent is sound** — hexagonal layering, domain ports, capability-driven broker plugins, and a shared replay engine are genuinely present. The **runtime realization is unsafe for real money** due to:

- Three competing OMS instances (ephemeral API session vs DI singleton vs composer bypass)
- Live mark-to-market never wired (`TICK` → PnL only in tests)
- Zero-parity violations (indicators, exits, replay market data)
- Silent degradation (`None`/empty instead of fail-fast)
- 85% of `brokers/common/` as deprecated shims with layering inversion (partially fixed Phase 0)

**Comparable quality target:** Pandas/SQLAlchemy-level discoverability — users work with `Instrument`, not `BrokerGateway`.

---

## 2. Current vs Proposed Architecture

### Current (as-found)

```
CLI / API / tradex.connect
    ├── Stack A: ephemeral OMS (session_bridge, per-request, unsubscribed)
    ├── Stack B: DI TradingContext (bus-wired, used for reads)
    └── Stack C: ExecutionComposer (modify/cancel, bypasses OMS)

brokers/common/ ──(shim)──> tradex/runtime/   [INVERSION — Phase 0 partial fix]
analytics/pipeline/features.py  [SMA RSI/ATR — non-canonical]
src/domain/indicators/*         [Wilder — canonical but unused on trading path]
ReplayEngine                    [private SimulatedPosition, no TICK events]
```

### Proposed (target)

```
interfaces/{sdk,cli,rest}
    └── application/ (ONE OMS singleton, ONE RiskManager, ExitManager)
            └── domain/ (rich Instrument, ports, Wilder indicators, enforced EventType)
                    └── infrastructure/ (event_bus, idempotency, persistence)
                            └── brokers/{dhan,upstox,paper} (plugins via BrokerAdapter)
```

**Live ≡ Replay seam:** `MarketDataSource` port → same `Quote`/`TICK` events → same `PositionManager` + indicators + `ExitManager`.

---

## 3. Dependency Graph

### Before (violations highlighted)

| From | To | Issue |
|------|-----|-------|
| `brokers.common.gateway` | `tradex.runtime` | Layering inversion (fixed: capabilities canonical in `brokers.common.broker_capabilities`) |
| `application.composer` | `tradex.runtime`, `cli` | Upward dependency |
| `domain.universe.Session` | composition root in domain | Mis-layered (belongs `application/`) |
| `api place_order` | ephemeral OMS | State desync with DI reads |

### After (target)

All edges point **inward**: `interfaces → application → domain ← infrastructure/brokers` (implement ports only).

See diagrams: [`diagrams/dependency-before.mmd`](diagrams/dependency-before.mmd), [`diagrams/dependency-after.mmd`](diagrams/dependency-after.mmd).

---

## 4. Domain Model & Object Hierarchy

### Rich object tree (target)

| Object | Owner layer | Key behaviors |
|--------|-------------|---------------|
| `Instrument` / `Equity` / `Index` / `Future` / `Option` | Domain | `quote`, `history`, `subscribe`, `depth`, **`buy/sell`** |
| `OptionChain` | Domain | `atm`, `calls`, `puts`, `pcr`, `greeks`, cached construction |
| `Portfolio` | Domain aggregate | Single owner of positions; service = read adapter |
| `Position` / `Order` / `Trade` | Domain VOs | Frozen; no lifecycle state on `Position` VO |
| `Quote` / `MarketDepth` / `HistoricalSeries` | Domain VOs | Normalized at adapter boundary once |
| `Watchlist` | Domain | **Missing — add** |

### Critical gaps (current)

1. **`Instrument.buy()` does not exist** — execution on `Session` only (`domain/universe.py`)
2. **`Instrument` = `InstrumentRecord` alias** — silent type collision (`entities/instrument_record.py:48`)
3. **Option greeks return `Greeks.zero()`** when no leg — silent correctness trap
4. **12+ methods return `None`** on missing provider instead of fail-fast

See [`diagrams/object-hierarchy.mmd`](diagrams/object-hierarchy.mmd).

---

## 5. Package / Module Hierarchy

| Current | Proposed | Phase |
|---------|----------|-------|
| `src/domain/` | `domain/` | Keep |
| `application/` | `application/` | Keep; move `Session`/`Universe` here |
| `brokers/common/` (90 shims) | collapse to deprecation shim | Phase 4 |
| `api/` | `interfaces/rest/` | Phase 1 scaffold ✅ |
| `cli/` | `interfaces/cli/` | Phase 1 scaffold ✅ |
| `tradex/` | `interfaces/sdk/` | Phase 1 scaffold ✅ |
| `infrastructure/` | `infrastructure/` | Keep; canonical idempotency |
| `analytics/` + `datalake/` | consolidate | Phase 3 |
| `poc/`, `providers/` | delete | Phase 5 |
| `runtime/` + `tradex/runtime/` | merge | Phase 5 |
| — | `shared/` | Phase 1 scaffold ✅ |

---

## 6. Class Responsibilities

### OMS spine (single owner required)

| Class | Responsibility | Current issue |
|-------|----------------|---------------|
| `OrderManager` | Order lifecycle, idempotency ledger, trade dedup | 3 instances; auto-gen `correlation_id` |
| `PositionManager` | Position book, PnL from fills + LTP | LTP never fed in production |
| `RiskManager` | Pre-trade risk, kill switch | 3 separate instances |
| `ProcessedTradeRepository` | Exactly-once trade application | Not wired on API place path |
| `ExecutionComposer` | Should be **transport only** | Currently bypasses OMS for modify/cancel |

### Market data

| Class | Responsibility | Current issue |
|-------|----------------|---------------|
| Broker feed adapters | Raw → `Quote`/`MarketDepth` | Shotgun normalization (3+ paths) |
| `EventBus` | Sync dispatch, DLQ, metrics | Handlers on WS thread; `AsyncEventBus` unused |
| `MarketBridge` | Outbound WS from bus | Subscribes orphan types (fixed: added to `EventType`) |
| `LatestQuoteStore` | **Missing** — should own latest quote per symbol | Quotes ephemeral, GC'd |

### Analytics

| Class | Responsibility | Current issue |
|-------|----------------|---------------|
| `FeaturePipeline` | Indicator + feature composition | Uses non-standard SMA RSI/ATR |
| `ReplayEngine` | Bar-by-bar replay | Private `SimulatedPosition`; no TICK events |
| `StrategyPipeline` | Signal generation | Shared — good |
| `ExitManager` | **Missing in live** | Backtest exits via SL/target; live has none |

---

## 7. Object Interaction Diagrams

See [`diagrams/oms-execution-flow.mmd`](diagrams/oms-execution-flow.mmd) for order placement (current broken vs target).

---

## 8. Event Flow Diagrams

### Canonical events (enforced Phase 0)

Added to `EventType`: `QUOTE`, `DEPTH_20`, `DEPTH_200`, `TRADE_FILLED`.  
`EventBus` warns on unknown `event_type` when `enforce_event_types=True`.  
`DomainEvent.payload` frozen via `MappingProxyType`.

### Production gap

No subscriber wires `TICK` → `PositionManager.update_ltp` outside tests.

See [`diagrams/event-flow.mmd`](diagrams/event-flow.mmd).

---

## 9. Data Lifecycle Diagrams

**Target pipeline:**

```
Exchange → BrokerAdapter → Normalizer → Quote/MarketDepth (domain)
    → EventBus(TICK/DEPTH) → [Indicators, PositionManager.update_ltp, Risk, ExitManager]
    → Strategy → OMS → Broker → Fill → TRADE_APPLIED → Position → Portfolio → Analytics → Persistence
```

**Current breaks:** normalization duplicated; indicators not on stream path; replay bypasses bus for market data.

See [`diagrams/data-lifecycle.mmd`](diagrams/data-lifecycle.mmd).

---

## 10. Broker Plugin Architecture

### Patterns in use (good)

- `BrokerAdapter` protocol (`domain.ports.broker_adapter`)
- `BrokerCapabilities` matrix (`brokers.common.broker_capabilities` — canonical Phase 0)
- `Extension` registry (`domain.extensions`) — e.g. `DhanDepth20Extension`
- Self-registering `adapter_factory` (ADR-007)

### Patterns broken

- Upstox bypasses `BrokerFactory`; `_ensure_extended()` missing → `AttributeError`
- Two extension mechanisms (`Extension` registry vs `*ExtendedCapabilities`)
- Idempotency: `infrastructure/idempotency` built but brokers use local in-memory dicts

See [`diagrams/broker-plugin.mmd`](diagrams/broker-plugin.mmd).

---

## 11. Historical and Live Data Lifecycle

| Stage | Live | Backtest/Replay | Parity? |
|-------|------|-----------------|---------|
| Bar/tick source | Broker WS | Parquet/datalake | Different objects |
| Normalization | Per-feed ad hoc | `FeaturePipeline` on DataFrame | No |
| Indicators | Not wired on stream | `analytics/pipeline` (SMA) | No |
| Signals | `StrategyPipeline` | Same | Partial |
| Exits | None | SL/target in `ReplayEngine` | **No** |
| Positions | `PositionManager` (stale LTP) | `SimulatedPosition` | **No** |

**Fix:** `MarketDataSource` port + `ReplayDataSource` emitting identical domain events.

See [`diagrams/live-replay-seam.mmd`](diagrams/live-replay-seam.mmd).

---

## 12. Public SDK Design

```python
import tradex  # interfaces.sdk re-exports

session = tradex.connect("paper")
reliance = session.universe.equity("RELIANCE")
reliance.buy(10, price=2500)
chain = reliance.option_chain()
chain.atm.delta
```

**Rules:**
- Single entrypoint: `tradex.connect`
- No `BrokerClient`/`Gateway`/REST in public API
- `Instrument` carries injected ports; `buy()` delegates to `ExecutionProvider` via session

---

## 13. Design Pattern Justification

| Pattern | Where | Why |
|---------|-------|-----|
| Hexagonal / Ports & Adapters | `domain.ports.*`, broker plugins | Hide infrastructure |
| Capability matrix | `BrokerCapabilities` | No `if broker == "dhan"` |
| Extension objects | `domain.extensions` | Broker-specific features behind registry |
| Abstract factory | `adapter_factory`, `Dhan BrokerFactory` | Plugin registration |
| Observer | `EventBus` | Decouple producers/consumers |
| Singleton (process) | OMS `TradingContext` | **Required** — one order book |
| Repository | `ProcessedTradeRepository`, order store | Durable idempotency |
| Strategy | `StrategyPipeline` | Pluggable signal logic |

**Reject:** duplicate OMS instances, second composition root in CLI, manager classes exposing broker internals.

---

## 14. Testing Strategy

### Pyramid (real-money safe)

1. **Architecture** (`tests/architecture/*`) — import-linter, domain isolation — gate every PR
2. **Domain unit** — pure math, VOs, state machines
3. **Contract** — parametrized per broker adapter vs `BrokerAdapter`/`DataProvider`/`ExecutionProvider`
4. **Integration** — `PaperGateway` (real deterministic adapter), not `MockBrokerGateway` with `ltp=100`
5. **Replay parity** — `paper_replay_parity`, `live_backtest_parity` markers
6. **Chaos/resilience** — `MockFailingBroker` only where failure injection is the subject
7. **Performance** — `pre_prod` marker

### Unsafe mocks to eliminate

- `tests/e2e/fixtures/mock_brokers.py` — empty history, fixed LTP
- e2e TICK handler expecting `payload["ltp"]` while Dhan emits `{"quote": Quote}`

---

## 15. Performance Recommendations

1. Wire `AsyncEventBus` or document sync bus + offload slow handlers to bounded queues
2. `LatestQuoteStore` — stop per-tick `Quote` allocation/GC
3. Shard `EventBus` subscriber locks by event type
4. Replace 10k LRU idempotency with durable dedup for long sessions
5. Cache `OptionChain.calls`/`puts` construction (N+1 per property read today)
6. Single normalizer at adapter boundary (strict mode, never zero-fill LTP)

---

## 16. Migration Roadmap

| Phase | Objective | Gate |
|-------|-----------|------|
| **0** ✅ | Layering fix (capabilities), EventType enforcement, payload freeze | `lint-imports`, architecture tests |
| **1** ✅ | `interfaces/`, `shared/` scaffold | imports resolve |
| **2** ✅ | Single OMS singleton; modify/cancel via OMS; tradebook PnL from PositionManager | `tests/architecture/test_phase2_oms_singleton.py` green; `lint-imports` clean |
| **3** | Zero-parity (indicators, exits, TICK→PnL, replay bus) | parity markers green |
| **4** | Broker plugin consolidation | per-adapter contract tests |
| **5** | DX (`Instrument.buy`), e2e on PaperGateway, delete poc/providers | CLI/REST parity |
| **6** | Continuous review loop | DoD checklist |

---

## 17. Risk Analysis

| Risk | Severity | Mitigation |
|------|----------|------------|
| Fills never update queried book | Critical | Phase 2 singleton OMS |
| Duplicate orders on retry | Critical | Mandatory `correlation_id`; durable idempotency |
| Stale/frozen live PnL | Critical | Phase 3 TICK subscription |
| Backtest profit from exits live can't realize | Critical | Phase 3 ExitManager + signal contract |
| Wrong indicator math | High | Wire `domain.indicators` everywhere |
| Upstox extended crash | High | Fix or remove `_ensure_extended` |
| False e2e confidence | High | PaperGateway + real payload shapes |

---

## 18. Technical Debt Eliminated (Phase 0–2)

- `brokers.common.gateway` no longer imports `tradex.runtime` (capabilities canonical in `brokers.common.broker_capabilities`)
- `tradex.runtime.capabilities` re-exports from brokers (correct dependency direction)
- Orphan event types added to `EventType` enum
- `DomainEvent.payload` immutable at top level
- `EventBus` warns on unknown event types
- `interfaces/{sdk,cli,rest}` and `shared/` scaffolded
- **Phase 2 — OMS singleton consolidated:**
  - `application/oms/process_context.py` — process-wide OMS registry; `register_oms_context`/`get_oms_context`
  - CLI `oms_setup.register_oms_services` and FastAPI `api/main.create_app` register the `TradingContext` as the singleton
  - `session_bridge.build_oms_service` now resolves the shared context (no ephemeral per-`tradex.connect` OMS that lost fills)
  - API `POST /orders` forwards `correlation_id`, no longer discards the OMS on `session.close()`
  - `OrderManager.modify_order` added; API modify/cancel route through the OMS (kill-switch guarded) using `ExecutionComposer` as transport only
  - `GET /tradebook` PnL now sourced from the single `PositionManager` book
  - `Order.with_price/with_quantity/with_order_type` helpers added
  - Gate: `tests/architecture/test_phase2_oms_singleton.py` (3 tests) + `lint-imports` clean

---

## 19. Remaining Future Improvements

- Collapse `brokers/common/` shim wall (Phase 4)
- Move `Session`/`Universe` to `application/`
- Delete `Instrument = InstrumentRecord` alias
- `InstrumentFactory` → deprecated aggregate path
- Consolidate `SubscriptionState` duplicate enums
- Graduate `poc/` ML methodology to `analytics/ml/`; delete standalone backtest
- `Watchlist` aggregate
- Deep-freeze event payloads if nested mutation becomes an issue

---

## 20. Definition of Done (Measurable)

- [x] `lint-imports` zero forbidden edges
- [x] One OMS + one RiskManager per process; integration test proves fills update queried book (`test_phase2_oms_singleton.py`)
- [ ] `backtest ≡ replay ≡ live` on canonical indicators + SL/target exits
- [ ] No `MockBrokerGateway` in flow tests
- [ ] Live `TICK` → PnL in production
- [ ] `brokers/common` ≤ 1 shim file; single idempotency on order path
- [ ] `Instrument.buy()` works; broker internals unreachable from `tradex`
- [ ] No silent `None`/empty without explicit `NullProvider`

---

## Appendix: Ranked Findings (Full Board)

1. Three competing OMS instances — stale PnL
2. Idempotency per-instance, opt-out by default
3. Modify/cancel bypass OMS
4. Live PnL never updates from ticks
5. e2e false coverage on TICK payload shape
6. Zero-parity broken for exits
7. Zero-parity broken for indicators (3 implementations)
8. Upstox extended path crashes
9. Idempotency service unused on live order path
10. brokers/common shim wall + layering inversion (partial fix)
11. Instrument.buy() missing; Session in wrong layer
12. application leaks broker concerns via composer

---

*This document supersedes prior architecture docs for planning purposes. Implementation tracked per migration phases above.*
