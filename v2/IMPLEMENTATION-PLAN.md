# TradeXV2 — Multi-Agent Implementation Plan

> **Zero-parity, TDD-driven, zero-copy implementation under `v2/`.**
> Existing code is reference only. Fresh implementation from spec.

---

## Constraints

| Rule | Source |
|------|--------|
| **TDD Iron Law** | No production code without a failing test first. Watch it fail. Minimal code to pass. |
| **Ponytail** | Simplest solution that works. YAGNI. No over-engineering. Fewest files possible. |
| **Zero-copy** | Frozen dataclasses for all messages/entities. No defensive copying. |
| **Zero-parity** | Single ExecutionEngine. Only FillSource + Clock differ per mode. |
| **Fresh implementation** | Don't copy from existing v2/ code. Use as reference only. |
| **Dependency rule** | domain → nothing inward. application → domain+shared. infrastructure → domain+shared. |

---

## Dependency Graph

```
                    ┌─────────────────┐
                    │   PHASE 1       │
                    │   Foundation    │
                    │                 │
                    │ ┌─────────────┐ │    PARALLEL (no deps)
                    │ │ Domain      │ │
                    │ │ Model       │ │
                    │ └──────┬──────┘ │
                    │ ┌──────┴──────┐ │
                    │ │ Shared      │ │
                    │ │ Layer       │ │
                    │ └──────┬──────┘ │
                    │ ┌──────┴──────┐ │
                    │ │ Port        │ │
                    │ │ Protocols   │ │
                    │ └──────┬──────┘ │
                    └────────┼────────┘
                             │
                    ┌────────▼────────┐
                    │   PHASE 2       │
                    │   Infrastructure│
                    │                 │
                    │ ┌─────────────┐ │    PARALLEL (independent)
                    │ │ MessageBus  │ │◄─── depends on: domain messages
                    │ └──────┬──────┘ │
                    │ ┌──────┴──────┐ │
                    │ │ Component   │ │◄─── depends on: domain
                    │ │ + Lifecycle │ │
                    │ └──────┬──────┘ │
                    │ ┌──────┴──────┐ │
                    │ │ Clock       │ │◄─── depends on: domain
                    │ └──────┬──────┘ │
                    │ ┌──────┴──────┐ │
                    │ │ Idempotency │ │◄─── depends on: domain
                    │ └──────┬──────┘ │
                    │ ┌──────┴──────┐ │
                    │ │ Observability│ │◄─── depends on: domain
                    │ └──────┬──────┘ │
                    └────────┼────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐ ┌───▼──────────┐ ┌─▼──────────────┐
     │   PHASE 3A     │ │  PHASE 3B    │ │  PHASE 3C      │
     │   OMS Core     │ │  Risk +      │ │  Broker        │
     │                │ │  Idempotency │ │  Common        │
     │ ┌────────────┐ │ │              │ │                │
     │ │ OrderMgr   │ │ │ ┌──────────┐ │ │ ┌────────────┐ │
     │ └────────────┘ │ │ │ RiskMgr  │ │ │ │ Capabilities│ │
     │ ┌────────────┐ │ │ └──────────┘ │ │ └────────────┘ │
     │ │ PositionMgr│ │ │ ┌──────────┐ │ │ ┌────────────┐ │
     │ └────────────┘ │ │ │ Rules    │ │ │ │ Transport  │ │
     │ ┌────────────┐ │ │ └──────────┘ │ │ └────────────┘ │
     │ │ TradingCache│ │ │ ┌──────────┐ │ │ ┌────────────┐ │
     │ └────────────┘ │ │ │ Idempot. │ │ │ │ WireMapper │ │
     │ ┌────────────┐ │ │ │ Guard    │ │ │ └────────────┘ │
     │ │ TradingCtx │ │ │ └──────────┘ │ │ ┌────────────┐ │
     │ └────────────┘ │ │              │ │ │ SymbolResol│ │
     └───────┬────────┘ └──────┬───────┘ └──────┬───────┘
             │                 │                 │
             └────────┬────────┘                 │
                      │                          │
             ┌────────▼──────────────────────────▼────┐
             │   PHASE 4                              │
             │   Execution Engine (THE SPINE)          │
             │                                        │
             │ ┌────────────────────────────────────┐ │
             │ │ ExecutionEngine                    │ │
             │ │ (RiskGate → Idempotency → FillSrc) │ │
             │ └────────────────────────────────────┘ │
             │ ┌────────────┐ ┌────────────────────┐ │
             │ │ FillSource │ │ ReconciliationEng  │ │
             │ │ Protocol   │ │ (pure compare)     │ │
             │ └────────────┘ └────────────────────┘ │
             │ ┌────────────────────────────────────┐ │
             │ │ Four Implementations:              │ │
             │ │ Replay / Simulated / Paper / Broker│ │
             │ └────────────────────────────────────┘ │
             └──────────────────┬─────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
     ┌────────▼───────┐ ┌──────▼──────┐ ┌────────▼───────┐
     │  PHASE 5A      │ │  PHASE 5B   │ │  PHASE 5C      │
     │  Paper Broker  │ │  Dhan Broker│ │  Upstox Broker │
     │  (6 files)     │ │  (8 files)  │ │  (8 files)     │
     │                │ │             │ │                │
     │ Gateway→Conn→  │ │ Gateway→    │ │ Gateway→       │
     │ SubAdapters    │ │ Conn→       │ │ Conn→          │
     │                │ │ SubAdapters │ │ SubAdapters    │
     └───────┬────────┘ └──────┬──────┘ └───────┬────────┘
             │                 │                 │
             └────────┬────────┘─────────────────┘
                      │
             ┌────────▼────────┐
             │   PHASE 6       │
             │   Runtime       │
             │                 │
             │ ┌─────────────┐ │
             │ │ RuntimeFact.│ │
             │ └─────────────┘ │
             │ ┌─────────────┐ │
             │ │ PluginDiscov│ │
             │ └─────────────┘ │
             │ ┌─────────────┐ │
             │ │ ExecTarget  │ │
             │ └─────────────┘ │
             │ ┌─────────────┐ │
             │ │ Startup     │ │
             │ └─────────────┘ │
             └────────┬────────┘
                      │
              ┌───────┼───────┐
              │               │
     ┌────────▼──────┐ ┌──────▼────────┐
     │  PHASE 7A     │ │  PHASE 7B     │
     │  Analytics    │ │  Interfaces   │
     │               │ │               │
     │ FeaturePipe   │ │ CLI (Click)   │
     │ StrategyEng   │ │ TUI (Textual) │
     │ BacktestEng   │ │ FastAPI       │
     │ ReplayEng     │ │ MCP Server    │
     │ PaperEng      │ │               │
     │ LiveEng       │ │               │
     │ ScannerSuite  │ │               │
     │ Reports       │ │               │
     └───────┬───────┘ └───────┬───────┘
             │                 │
             └────────┬────────┘
                      │
             ┌────────▼────────┐
             │   PHASE 8       │
             │   Integration   │
             │   + Parity      │
             │                 │
             │ E2E Tests       │
             │ Parity Gate     │
             │ Architecture    │
             │ Mutation        │
             └─────────────────┘
```

---

## Parallel Execution Map

### Wave 1: Foundation (3 agents parallel)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **A1** | `domain/` | entities, value_objects, enums, messages, events, commands | nothing |
| **A2** | `shared/` | logging, config, types, errors | nothing |
| **A3** | `domain/ports/` | all Protocol definitions | A1 (types) |

**Exit criteria:** All domain types importable. Protocols testable. Shared layer works.

### Wave 2: Infrastructure (5 agents parallel)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **B1** | `infrastructure/message_bus/` | MessageBus, MessageRouter, MessageLog | A1 (messages) |
| **B2** | `infrastructure/component/` | Component base, LifecycleManager | A1 (domain) |
| **B3** | `infrastructure/clock.py` | SystemClock, FakeClock | A1 (domain) |
| **B4** | `infrastructure/idempotency/` | IdempotencyGuard | A1 (domain) |
| **B5** | `infrastructure/observability/` | Metrics, Audit, Health | A1 (domain) |

**Exit criteria:** MessageBus routes messages. Components follow lifecycle. Clock works.

### Wave 3: Application Core (3 agents parallel)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **C1** | `application/oms/` | OrderManager, PositionManager, TradingCache, TradingContext | B1, B2 |
| **C2** | `application/risk/` | RiskManager, RiskRules, RiskContext | B1, B2 |
| **C3** | `plugins/brokers/common/` | Capabilities, Transport, WireMapper, SymbolResolver | A1, A3 |

**Exit criteria:** Order FSM works. RiskGate rejects oversized orders. Broker common infra ready.

### Wave 4: Execution Engine (1 agent, sequential)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **D1** | `application/execution/` | ExecutionEngine, FillSource protocol, 4 implementations | C1, C2, B4 |

**Exit criteria:** Order spine works end-to-end. Four-mode parity test passes. No bypass paths.

### Wave 5: Broker Plugins (3 agents parallel)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **E1** | `plugins/brokers/paper/` | Gateway, Connection, 5 sub-adapters | C3, D1 |
| **E2** | `plugins/brokers/dhan/` | Gateway, Connection, 5 sub-adapters, auth, wire | C3, D1 |
| **E3** | `plugins/brokers/upstox/` | Gateway, Connection, 5 sub-adapters, auth, wire | C3, D1 |

**Exit criteria:** All 3 brokers pass AdapterTestHarness.

### Wave 6: Runtime + Reconciliation (2 agents parallel)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **F1** | `runtime/` | RuntimeFactory, PluginDiscovery, ExecutionTarget, Startup | D1, E1-E3 |
| **F2** | `application/reconciliation/` | ReconciliationEngine (pure compare) | C1, A1 |

**Exit criteria:** `tradex replay`, `tradex backtest`, `tradex paper` run full sessions.

### Wave 7: Analytics + Interfaces (2 agents parallel)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **G1** | `application/analytics/` | FeaturePipeline, StrategyEngine, Backtest/Replay/Paper/Live engines, Scanner, Reports | D1, B1 |
| **G2** | `interface/` | CLI (Click), TUI (Textual), FastAPI, MCP | F1 |

**Exit criteria:** Full analytics suite works. CLI/TUI/API functional.

### Wave 8: Integration + Parity (1 agent, sequential)

| Agent | Module | Files | Depends On |
|-------|--------|-------|------------|
| **H1** | `tests/` | E2E, parity, architecture, integration tests | All |

**Exit criteria:** CI green. 147/147 capabilities COVERED. Production checklist done.

---

## TDD Workflow Per Agent

Each agent follows the **Red-Green-Refactor** cycle:

```
1. RED:    Write ONE failing test
2. VERIFY: Watch it fail (mandatory)
3. GREEN:  Write minimal code to pass
4. VERIFY: Watch it pass (mandatory)
5. REFACTOR: Clean up (optional, keep green)
6. REPEAT: Next failing test
```

### Per-Agent Output Contract

Each agent produces:
```
tests/unit/{module}/test_{component}.py    # Tests (written FIRST)
src/{module}/{component}.py                # Implementation (written AFTER tests fail)
```

### Test Naming Convention

```python
def test_{component}_{behavior}_{condition}():
    """One behavior. Clear name. Shows intent."""
    # Arrange
    # Act
    # Assert
```

---

## File Count Target

| Module | Target Files | Actual |
|--------|-------------|--------|
| domain/ | ~10 | — |
| shared/ | ~4 | — |
| infrastructure/ | ~12 | — |
| application/oms/ | ~5 | — |
| application/risk/ | ~3 | — |
| application/execution/ | ~6 | — |
| application/analytics/ | ~15 | — |
| application/reconciliation/ | ~1 | — |
| plugins/brokers/common/ | ~5 | — |
| plugins/brokers/paper/ | ~6 | — |
| plugins/brokers/dhan/ | ~8 | — |
| plugins/brokers/upstox/ | ~8 | — |
| plugins/exchanges/nse/ | ~2 | — |
| runtime/ | ~5 | — |
| datalake/ | ~8 | — |
| interface/ | ~6 | — |
| config/ | ~3 | — |
| tradex/ | ~3 | — |
| **Total** | **~110** | — |

---

## Acceptance Criteria Per Phase

### Phase 1: Foundation
- [ ] All domain types importable from `domain/`
- [ ] Frozen dataclasses: `isinstance(obj, FrozenInstanceError)` check
- [ ] Decimal for Money/Price (no float)
- [ ] All Port Protocols defined and testable
- [ ] Shared logging produces JSON

### Phase 2: Infrastructure
- [ ] MessageBus: publish → subscriber receives message
- [ ] MessageBus: unsubscribe stops delivery
- [ ] Component: initialize → start → stop lifecycle
- [ ] LifecycleManager: startup order enforced
- [ ] Clock: SystemClock.now() returns real time
- [ ] Clock: FakeClock.advance() moves time
- [ ] IdempotencyGuard: duplicate correlation_id → prior result

### Phase 3: Application Core
- [ ] OrderManager: FSM transitions validated
- [ ] OrderManager: illegal transition → fail-fast
- [ ] PositionManager: fill → correct position
- [ ] TradingCache: cache-then-publish verified
- [ ] RiskManager: oversized order → RISK_REJECTED
- [ ] RiskManager: kill switch → all orders rejected
- [ ] Broker common: WireMapper roundtrip

### Phase 4: Execution Engine
- [ ] ExecutionEngine: order → risk check → fill source → fill
- [ ] ExecutionEngine: risk denied → no venue call
- [ ] ExecutionEngine: idempotent on correlation_id
- [ ] Four-mode parity: same FSM in REPLAY/BACKTEST/PAPER/LIVE
- [ ] No bypass paths: architecture test passes
- [ ] ReconciliationEngine: drift detection correct

### Phase 5: Broker Plugins
- [ ] Paper: AdapterTestHarness pass
- [ ] Dhan: AdapterTestHarness pass (sandbox)
- [ ] Upstox: AdapterTestHarness pass (sandbox)
- [ ] Plugin discovery finds all 3 brokers
- [ ] Entry points registered in pyproject.toml

### Phase 6: Runtime
- [ ] RuntimeFactory: build from config
- [ ] PluginDiscovery: entry-point resolution
- [ ] ExecutionTarget: FillSource + Clock per mode
- [ ] Startup: risk-bound + environment freeze
- [ ] `tradex replay` runs full session
- [ ] `tradex backtest` runs full session
- [ ] `tradex paper` runs full session

### Phase 7: Analytics + Interfaces
- [ ] FeaturePipeline: bar → features → enriched bar
- [ ] StrategyEngine: register → route → emit order
- [ ] BacktestEngine: historical simulation produces metrics
- [ ] ReplayEngine: MessageLog → identical state
- [ ] CLI: all commands functional
- [ ] TUI: renders correctly
- [ ] FastAPI: health endpoint responds

### Phase 8: Integration + Parity
- [ ] E2E: startup → order → fill → reconcile
- [ ] Parity gate: four-mode FSM identical
- [ ] Architecture: import linter passes
- [ ] Architecture: no bypass order paths
- [ ] Architecture: no god classes (degree ≤ 50)
- [ ] Replay determinism: log → identical cache
- [ ] 85%+ test coverage
- [ ] 147/147 capabilities COVERED

---

## Execution Commands

### Start a Wave (parallel agents)

```bash
# Wave 1: Foundation (3 agents)
mimo run --description "Domain model TDD" --prompt "..."
mimo run --description "Shared layer TDD" --prompt "..."
mimo run --description "Port protocols TDD" --prompt "..."

# Wave 2: Infrastructure (5 agents)
mimo run --description "MessageBus TDD" --prompt "..."
# ... etc
```

### Verify a Wave

```bash
cd /Users/apple/Downloads/Trade_XV2/v2
python -m pytest tests/unit/{module}/ -x -v
```

### Check Architecture Contracts

```bash
python -m importlinter --config pyproject.toml
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Agent produces code before test | TDD checklist in prompt: "Write test FIRST. Watch fail. Then implement." |
| Agent copies from existing code | Prompt: "Fresh implementation. Existing v2/ is reference only." |
| Agents produce incompatible interfaces | Wave exit criteria: interface contracts verified before next wave |
| Parity broken | Phase 4 parity gate: single test that runs same order through all 4 modes |
| God classes | Architecture test: dependency degree ≤ 50 per class |
| Import violations | import-linter in CI: domain purity, application isolation |

---

## Estimated Timeline

| Wave | Duration | Agents | Deliverable |
|------|----------|--------|-------------|
| 1: Foundation | 1-2 days | 3 | Domain, shared, ports |
| 2: Infrastructure | 1-2 days | 5 | MessageBus, lifecycle, clock, idempotency |
| 3: Application Core | 2-3 days | 3 | OMS, risk, broker common |
| 4: Execution Engine | 1-2 days | 1 | The spine + fill sources |
| 5: Broker Plugins | 2-3 days | 3 | Paper, Dhan, Upstox |
| 6: Runtime | 1 day | 2 | Composition root + reconciliation |
| 7: Analytics + Interfaces | 2-3 days | 2 | Full analytics + CLI/TUI/API |
| 8: Integration + Parity | 2-3 days | 1 | E2E, parity, architecture |
| **Total** | **12-19 days** | **8 unique** | **Full framework** |
