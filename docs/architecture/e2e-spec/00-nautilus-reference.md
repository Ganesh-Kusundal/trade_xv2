# 00 — Nautilus Reference Mapping

**Source of truth for Nautilus concepts:**  
`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/architecture.md`  
`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/overview.md`  
`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/message_bus.md`  
`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/execution.md`  
`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/cache.md`  
`/Users/apple/Downloads/nautilus_trader-develop/docs/concepts/live.md`  
`/Users/apple/Downloads/nautilus_trader-develop/nautilus_trader/system/kernel.py`

---

## 1. What we adopt (contracts, not code)

| Nautilus concept | Why it matters for real money | TradeXV2 target name |
|---|---|---|
| **NautilusKernel** — common core for backtest / sandbox / live | One composition of engines; parity is structural | **TradeXKernel** (`runtime/`) |
| **MessageBus** — pub/sub + point-to-point + req/rep; immutable messages | Loose coupling without split-brain | **EventBus** (single substrate) |
| **Cache** — in-memory SoT for instruments, orders, positions, accounts, quotes | Risk/execution read the same state strategies see | **TradingCache** |
| **DataEngine** — cache-then-publish for quotes/trades/bars | Handler always sees latest cache value | **DataEngine** |
| **RiskEngine** — pre-trade + TradingState + Throttler | Fail-closed, burst-safe | **RiskEngine** (wraps today’s RiskManager) |
| **ExecutionEngine** — one engine; swap ExecutionClient | Zero-parity | **ExecutionEngine** (unifies live + SimulatedOMSAdapter) |
| **ExecutionClient** — venue adapter | Broker plugins stay at the edge | **BrokerAdapter** / gateway |
| **Clock** (`LiveClock` / `TestClock`) injected into every component | Deterministic replay | **TimeService** + `FakeClock` / `SystemClock` |
| **Component FSM** (PRE_INITIALIZED→…→DISPOSED) | Explicit lifecycle | **ComponentState** for engines |
| **Order FSM** (illegal transitions rejected) | Corrupt status = wrong money | Enforce via `ORDER_STATUS_TRANSITIONS` |
| **Reconciliation inside ExecutionEngine** | No inter-tick phantom positions | Hot-path reconcile |
| **Fail-fast / crash-only** for unrecoverable faults | Corrupt data > unavailable | Domain + risk fail-fast |
| **One node per process** | Global singletons / clocks | One TradeXKernel per process |

---

## 2. What we deliberately do **not** copy

| Nautilus feature | Reason |
|---|---|
| Rust/Cython core | Out of scope (project-overview §6) |
| Multi-venue crypto/DEX adapters | Indian brokers (Dhan/Upstox/Paper) via plugins |
| OrderEmulator / ExecAlgorithm / contingency OCO-OTO | Phase later; not required for first Zero-Parity cut |
| Redis-backed MessageBus state | Optional; SQLite ledger first |
| Nanosecond `UnixNanos` everywhere | Keep timezone-aware `datetime` + injected Clock; nanoseconds optional later |
| Actor trait dual registries | Keep Python Protocols + composition root |
| mimalloc / LMAX disruptor | Not a latency HFT stack; correctness first |

---

## 3. Component ↔ component map

```
Nautilus                          TradeXV2 (target)
─────────                         ─────────────────
NautilusKernel                    TradeXKernel (runtime composition)
MessageBus                        EventBusPort + one infra impl
Cache                             TradingCache (orders/positions/accounts/quotes)
DataEngine                        DataEngine (over DataProvider)
RiskEngine                        RiskEngine (RiskManagerPort + TradingState + Throttler)
ExecutionEngine                   ExecutionEngine (single; mode = FillSource)
LiveExecutionEngine               same ExecutionEngine + live FillSource
BacktestExecClient                SimulatedFillSource / PaperFillSource
ExecutionClient                   BrokerAdapter (orders + portfolio gateways)
Portfolio                         PortfolioService + PositionManager projection
Trader / Strategy                 TradingOrchestrator + StrategyPipeline
Actor                             domain ports + application use-cases
TestClock / LiveClock             FakeClock / SystemClock via TimeService
Environment.BACKTEST|SANDBOX|LIVE Environment enum (same three)
```

---

## 4. Nautilus flows we mirror exactly

### 4.1 Life of a quote (Nautilus architecture.md)

```
Adapter → channel → DataEngine → Cache.add_quote → MessageBus.publish → Strategy.on_quote
```

TradeXV2 target:

```
Broker WS / DataProvider → DataEngine → TradingCache.set_quote → EventBus(TICK|QUOTE) → Strategy / Orchestrator
```

**Invariant:** cache write **before** publish (handler can read cache safely).

### 4.2 Life of an order (Nautilus architecture.md)

```
Strategy → RiskEngine (pre-trade) → ExecutionEngine → ExecutionClient → Venue
Venue events → ExecutionClient → ExecutionEngine → Cache update → Strategy handlers
```

TradeXV2 target:

```
Orchestrator/OrderService → RiskEngine.check_order → ExecutionEngine → BrokerAdapter.submit
WS fills → BrokerAdapter → ExecutionEngine.apply_fill → TradingCache + PositionManager → EventBus(TRADE_APPLIED)
```

**Invariant:** risk denial never reaches the venue (`OrderDenied` / `RISK_REJECTED`).

### 4.3 Environments (Nautilus overview)

| Env | Data | Execution |
|---|---|---|
| Backtest | Historical catalog / bars | Simulated fill source, TestClock |
| Sandbox | Live market data | Simulated / paper fill source |
| Live | Live market data | Real BrokerAdapter |

**Invariant:** Strategy / risk / position code is identical across envs. Only **FillSource** + **Clock** + **DataSource** change at composition time.

---

## 5. Quality attributes (Nautilus weighting → TradeXV2)

Nautilus order: Reliability → Performance → Modularity → Testability → Maintainability → Deployability.

TradeXV2 (real-money Indian brokers) weights:

1. **Reliability / correctness** (fail-closed risk, FSM, Zero-Parity)
2. **Auditability** (ledger, immutable events, correlation_id)
3. **Modularity** (ports + plugins)
4. **Testability** (Clock injection, integration tests)
5. **Maintainability** (single bus, single idempotency)
6. **Performance** (after correctness; throttling before raw throughput)

---

## 6. Vocabulary (use these terms in all later docs)

| Term | Meaning |
|---|---|
| **Kernel** | Single process composition of Bus + Cache + Engines + Clock |
| **FillSource** | The only mode-specific piece of execution (live / paper / simulated) |
| **TradingCache** | Authoritative in-memory store read by risk, strategies, UI |
| **Hot-path reconcile** | Broker mass-status applied inside ExecutionEngine, not a timer service |
| **Zero-Parity** | Same engines + same semantics; env only swaps adapters |
| **Fail-closed** | Provider fault → deny order, never skip a check |
| **Expected Behavior Contract** | Inputs / outputs / timing / state transitions / failure modes for a path |
